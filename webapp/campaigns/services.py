import json
import logging

from agents import (
    AgentUpdatedStreamEvent,
    HandoffCallItem,
    MessageOutputItem,
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
)
from asgiref.sync import sync_to_async

from brand.models import Brand
from campaigns.agents.definitions import (
    coordinator_agent,
    image_analyser_agent,
    image_prompt_writer_agent,
    image_selector_agent,
    plan_builder_agent,
)
from campaigns.agents.tools import AgentContext
from campaigns.models import CampaignDraft, Conversation, Message

logger = logging.getLogger(__name__)


def _build_input_messages_sync(conversation: Conversation) -> list[dict]:
    """Convert stored conversation messages into the format expected by the SDK."""
    messages = conversation.messages.filter(role__in=['user', 'assistant']).order_by('created_at')
    return [{'role': msg.role, 'content': msg.content} for msg in messages]


def _build_agent_context_sync(conversation: Conversation) -> AgentContext:
    """Build the AgentContext from a conversation."""
    brand = Brand.objects.filter(project_id=conversation.project_id).first()
    return AgentContext(
        user_id=conversation.user_id,
        project_id=conversation.project_id,
        brand_id=brand.id if brand else None,
        conversation_id=conversation.id,
    )


def _create_user_message_sync(conversation, user_message):
    return Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content=user_message,
    )


def _create_step_message_sync(conversation, content, metadata):
    Message.objects.create(
        conversation=conversation,
        role=Message.Role.STEP,
        content=content[:2000],
        metadata=metadata,
    )


def _create_assistant_message_sync(conversation, content, agent_name):
    Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=content,
        metadata={'agent': agent_name},
    )


def _update_conversation_title_sync(conversation, title):
    conversation.title = title
    conversation.save(update_fields=['title'])


def _format_sse(event: str, data: str) -> str:
    """Format a server-sent event string."""
    return f'event: {event}\ndata: {data}\n\n'


async def _stream_agent_run(agent, input_text: str, ctx: AgentContext, conversation):
    """
    Run a single agent with the given input text and stream SSE events.

    Yields SSE-formatted strings and, as the very last item, yields a plain
    string (not SSE) containing the agent's full output text so the caller
    can pass it to the next step in the pipeline.
    """
    full_text = ''
    current_agent_name = agent.name

    result = Runner.run_streamed(
        starting_agent=agent,
        input=input_text,
        context=ctx,
        max_turns=10,
    )

    async for event in result.stream_events():
        if isinstance(event, AgentUpdatedStreamEvent):
            current_agent_name = event.new_agent.name
            yield _format_sse('agent_update', json.dumps({'agent': current_agent_name}))

        elif isinstance(event, RawResponsesStreamEvent):
            data = event.data
            if hasattr(data, 'type') and data.type == 'response.output_text.delta':
                delta = getattr(data, 'delta', '')
                if delta:
                    full_text += delta
                    yield _format_sse('text_delta', json.dumps({
                        'delta': delta,
                        'agent': current_agent_name,
                    }))

        elif isinstance(event, RunItemStreamEvent):
            item = event.item

            if isinstance(item, ToolCallItem):
                tool_name = getattr(item.raw_item, 'name', '')
                yield _format_sse('tool_call', json.dumps({
                    'tool': tool_name,
                    'agent': current_agent_name,
                }))

            elif isinstance(item, ToolCallOutputItem):
                output_text = item.output if isinstance(item.output, str) else str(item.output)
                tool_name = getattr(getattr(item, 'raw_item', None), 'name', '')
                await sync_to_async(_create_step_message_sync)(
                    conversation,
                    output_text,
                    {'agent': current_agent_name, 'step_type': 'tool_output', 'tool': tool_name},
                )
                yield _format_sse('tool_output', json.dumps({
                    'tool': tool_name,
                    'agent': current_agent_name,
                }))

            elif isinstance(item, MessageOutputItem):
                parts = []
                if hasattr(item.raw_item, 'content'):
                    for part in item.raw_item.content:
                        if hasattr(part, 'text'):
                            parts.append(part.text)
                if parts:
                    full_text = '\n'.join(parts)

    # Yield the accumulated text as the final (non-SSE) sentinel value so the
    # caller can chain it into the next pipeline step.
    yield full_text


async def _run_planning_pipeline(planner_output: str, conversation, ctx: AgentContext):
    """
    Run the four-step planning pipeline in a fixed, deterministic order:
      1. Image Selector  — picks seed images for each post
      2. Image Analyser  — describes each selected image visually
      3. Plan Builder    — assembles brief + images + analysis into a JSON plan
      4. Image Prompt Writer — writes generation prompts and renders the final Markdown plan

    Yields SSE events for each step. The final step's output is saved as the
    assistant message that the user sees and approves.
    """
    steps = [
        (
            image_selector_agent,
            lambda brief, **_: (
                f'Select seed images for each post in this campaign brief:\n\n{brief}'
            ),
        ),
        (
            image_analyser_agent,
            lambda brief, selector, **_: (
                f'Analyse these images that were selected for the campaign:\n\n{selector}'
            ),
        ),
        (
            plan_builder_agent,
            lambda brief, selector, analyser, **_: (
                f'Build the structured campaign plan.\n\n'
                f'## Campaign Brief\n{brief}\n\n'
                f'## Selected Images\n{selector}\n\n'
                f'## Image Analysis\n{analyser}'
            ),
        ),
        (
            image_prompt_writer_agent,
            lambda brief, selector, analyser, builder, **_: (
                f'Write image-generation prompts and compile the final campaign plan for user approval.\n\n'
                f'{builder}'
            ),
        ),
    ]

    outputs = {}  # keyed by step index
    step_keys = ['selector', 'analyser', 'builder', 'prompt_writer']

    for i, (agent, build_input) in enumerate(steps):
        kwargs = {
            'brief': planner_output,
            'selector': outputs.get('selector', ''),
            'analyser': outputs.get('analyser', ''),
            'builder': outputs.get('builder', ''),
        }
        input_text = build_input(**kwargs)

        step_output = ''
        async for chunk in _stream_agent_run(agent, input_text, ctx, conversation):
            if chunk.startswith('event:'):
                yield chunk
            else:
                # Plain string sentinel — the accumulated agent output
                step_output = chunk

        outputs[step_keys[i]] = step_output

    # Save the final plan (Image Prompt Writer output) as the assistant message
    final_plan = outputs.get('prompt_writer', '')
    if final_plan.strip():
        await sync_to_async(_create_assistant_message_sync)(
            conversation, final_plan.strip(), 'Image Prompt Writer'
        )

    yield _format_sse('done', json.dumps({'message': final_plan.strip()}))


async def run_agent_stream(conversation: Conversation, user_message: str):
    """
    Run the agent coordinator with streaming, yielding SSE-formatted events.

    Event types:
    - text_delta: Incremental text from the assistant
    - agent_update: A new agent has started running
    - tool_call: An agent is calling a tool
    - tool_output: A tool has returned a result
    - done: The run is complete, includes the full assistant message
    - error: An error occurred
    """
    # Save the user message and gather context via sync_to_async
    await sync_to_async(_create_user_message_sync)(conversation, user_message)
    input_messages = await sync_to_async(_build_input_messages_sync)(conversation)
    ctx = await sync_to_async(_build_agent_context_sync)(conversation)

    full_response_text = ''
    current_agent_name = 'Coordinator'

    try:
        result = Runner.run_streamed(
            starting_agent=coordinator_agent,
            input=input_messages,
            context=ctx,
            max_turns=25,
        )

        async for event in result.stream_events():
            if isinstance(event, AgentUpdatedStreamEvent):
                current_agent_name = event.new_agent.name
                yield _format_sse('agent_update', json.dumps({
                    'agent': current_agent_name,
                }))

            elif isinstance(event, RawResponsesStreamEvent):
                data = event.data
                if hasattr(data, 'type') and data.type == 'response.output_text.delta':
                    delta = data.delta if hasattr(data, 'delta') else ''
                    if delta:
                        full_response_text += delta
                        yield _format_sse('text_delta', json.dumps({
                            'delta': delta,
                            'agent': current_agent_name,
                        }))

            elif isinstance(event, RunItemStreamEvent):
                item = event.item

                if isinstance(item, ToolCallItem):
                    tool_name = getattr(item.raw_item, 'name', '')
                    yield _format_sse('tool_call', json.dumps({
                        'tool': tool_name,
                        'agent': current_agent_name,
                    }))

                elif isinstance(item, ToolCallOutputItem):
                    output_text = item.output if isinstance(item.output, str) else str(item.output)
                    tool_name = getattr(getattr(item, 'raw_item', None), 'name', '')

                    step_type = 'tool_output'
                    try:
                        output_data = json.loads(output_text)
                        if 'created_post_ids' in output_data:
                            step_type = 'posts_created'
                    except (json.JSONDecodeError, TypeError):
                        pass

                    await sync_to_async(_create_step_message_sync)(
                        conversation,
                        output_text,
                        {
                            'agent': current_agent_name,
                            'step_type': step_type,
                            'tool': tool_name,
                        },
                    )

                    yield _format_sse('tool_output', json.dumps({
                        'tool': tool_name,
                        'agent': current_agent_name,
                        'step_type': step_type,
                    }))

                elif isinstance(item, HandoffCallItem):
                    target = getattr(item.raw_item, 'name', '')
                    yield _format_sse('handoff', json.dumps({
                        'from_agent': current_agent_name,
                        'to_agent': target,
                    }))

                elif isinstance(item, MessageOutputItem):
                    text_parts = []
                    if hasattr(item.raw_item, 'content'):
                        for part in item.raw_item.content:
                            if hasattr(part, 'text'):
                                text_parts.append(part.text)
                    if text_parts:
                        full_response_text = '\n'.join(text_parts)

        # If the Planner just ran, kick off the deterministic planning pipeline.
        # The pipeline streams its own events and saves the final plan as the
        # assistant message, so we skip the normal save+done path.
        if current_agent_name == 'Planner':
            # Save the planner's brief as a step message (internal, not shown as
            # the final assistant response).
            if full_response_text.strip():
                await sync_to_async(_create_step_message_sync)(
                    conversation,
                    full_response_text.strip(),
                    {'agent': 'Planner', 'step_type': 'planning_brief'},
                )

            # Update title before the pipeline begins if still untitled.
            if not conversation.title:
                await sync_to_async(_update_conversation_title_sync)(
                    conversation, user_message[:60]
                )

            async for chunk in _run_planning_pipeline(full_response_text, conversation, ctx):
                yield chunk
            return

        # Normal path: save the final assistant message and emit done.
        if full_response_text.strip():
            await sync_to_async(_create_assistant_message_sync)(
                conversation, full_response_text.strip(), current_agent_name
            )

        # Update conversation title from first user message if still untitled
        if not conversation.title and full_response_text.strip():
            await sync_to_async(_update_conversation_title_sync)(
                conversation, user_message[:60]
            )

        yield _format_sse('done', json.dumps({
            'message': full_response_text.strip(),
        }))

    except Exception as e:
        logger.exception('Agent run failed')
        yield _format_sse('error', json.dumps({
            'error': str(e),
        }))


def create_campaign_posts(conversation: Conversation, draft: CampaignDraft):
    """
    Materialize a campaign draft into actual SocialMediaPost objects.
    Called when the user approves a campaign.
    """
    from social_media.models import (
        SocialMediaPost,
        SocialMediaPostMedia,
        SocialMediaPostPlatform,
    )
    from projects.models import Project

    project = Project.objects.get(pk=conversation.project_id)
    enabled_platforms = project.get_enabled_platforms()
    plan = draft.plan

    posts_data = plan.get('posts', [])
    created_posts = []

    for post_data in posts_data:
        post = SocialMediaPost.objects.create(
            user=conversation.user,
            project=conversation.project,
            title=post_data.get('title', 'Untitled'),
            shared_text=post_data.get('text', ''),
            topic=post_data.get('topic', ''),
            post_type=post_data.get('post_type', 'lifestyle'),
            status='draft',
        )

        platforms = post_data.get('platforms', enabled_platforms)
        for platform_name in platforms:
            if platform_name in enabled_platforms:
                SocialMediaPostPlatform.objects.create(
                    post=post,
                    platform=platform_name,
                    is_enabled=True,
                    use_shared_text=True,
                    use_shared_media=True,
                )

        for sort_order, img_id in enumerate(post_data.get('image_ids', [])):
            try:
                SocialMediaPostMedia.objects.create(
                    post=post,
                    image_id=img_id,
                    sort_order=sort_order,
                )
            except Exception:
                pass

        created_posts.append(post)
        draft.posts.add(post)

    draft.status = CampaignDraft.Status.CREATED
    draft.save(update_fields=['status'])

    return created_posts
