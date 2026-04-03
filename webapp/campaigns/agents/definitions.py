from agents import Agent, ModelSettings, WebSearchTool

from .tools import (
    AgentContext,
    create_posts,
    describe_image,
    generate_image,
    get_brand_info,
    get_enabled_platforms,
    list_image_groups,
    search_images,
    search_unsplash,
)

# ──────────────────────────────────────────────────────────────────────────────
# Leaf agents (no sub-agent dependencies)
# ──────────────────────────────────────────────────────────────────────────────

image_analyser_agent = Agent[AgentContext](
    name='Image Analyser',
    model='gpt-4o',
    instructions="""You analyse specific images that are given to you — you do NOT search or list images yourself.

You will be called with a list of images (each with an id, url, and optionally a description).
For each image in the list, call describe_image(image_id, image_url) to get a visual analysis.

Return a structured Markdown report:

## Image Analysis Report

For each image:
- **Image ID:** [id]
- **URL:** [url]
- **Visual description:** [what describe_image returned]

At the end, add a brief **Summary** of the overall visual style and subjects across all images,
and note which images would work best for product, lifestyle, or ad posts.
""",
    tools=[describe_image],
)

image_selector_agent = Agent[AgentContext](
    name='Image Selector',
    model='gpt-4o',
    instructions="""You select seed images for social media campaign posts. Every single post MUST receive at least one image — never leave a post without one.

For each post topic/type provided to you:
1. You must use list_image_groups and select suitable images.

You MUST return at least one image per post.

Return a structured Markdown list. For each post:

### Post: [topic] ([type])
- **image_id:** [integer DB id]
- **image_url:** [full absolute URL]
- **source:** media_library or unsplash
- **reason:** why this image fits the post

Include the image inline so the planner can preview it:
![](image_url)
""",
    tools=[list_image_groups],
    model_settings=ModelSettings(tool_choice='required')
)

image_prompt_writer_agent = Agent[AgentContext](
    name='Image Prompt Writer',
    model='gpt-4o-mini',
    instructions="""You write detailed AI image-generation prompts for social media campaign posts.

Given a list of post topics that need generated images:
1. Use get_brand_info to understand the brand's visual style, colors, and tone.
2. For each post, write a detailed English prompt that specifies:
   - Main subject (product, person, scene)
   - Visual style (photography, illustration, lifestyle, flat-lay, etc.)
   - Composition (close-up, wide shot, overhead, etc.)
   - Color palette aligned with the brand
   - Mood and atmosphere
   - Any platform hints (e.g. square composition for Instagram)

Return the prompts as a numbered Markdown list, one per post, labeled with the post topic.
Each prompt should be 2-4 sentences specific enough for an AI image generator.
""",
    tools=[get_brand_info],
)

# ──────────────────────────────────────────────────────────────────────────────
# Post Creator — runs autonomously after plan approval
# ──────────────────────────────────────────────────────────────────────────────

post_creator_agent = Agent[AgentContext](
    name='Post Creator',
    model='gpt-4o',
    instructions="""You create complete social media posts from an approved campaign plan. Work autonomously — do NOT ask for confirmation at any step.

Your workflow:

1. Read the approved plan carefully. For each post it contains:
   - topic, post_type, target platforms
   - seed_image_ids: list of integer DB IDs (images that guide generation)
   - image_generation_prompt: the prompt to use with generate_image

2. For EVERY post, call generate_image with:
   - prompt = the post's image_generation_prompt
   - seed_image_ids = the post's seed image IDs
   This generates a new AI image styled after the seed images. Record the returned image ID and URL.

3. Call get_brand_info to learn the brand voice and language.

4. Call get_enabled_platforms to confirm available platforms.

5. For every post, write engaging copy:
   - Match the brand voice and language.
   - Platform character limits: Twitter/X=280, Instagram=2200, LinkedIn=3000, Facebook=63206.
   - Include a call-to-action where appropriate.

6. Call create_posts ONCE with ALL posts. Each post must include:
   - title, text (the copy you wrote), topic, post_type
   - platforms list
   - image_ids: [the generated image ID from step 2]

7. After create_posts succeeds, output a Markdown summary:

## ✅ Campaign Created

For each post:
### [Post Title]
- **Platforms:** [list]
- **Generated image:** ![](generated_image_url)

**[N] posts created successfully and saved to drafts.**
""",
    tools=[get_brand_info, get_enabled_platforms, generate_image, create_posts],
)

# ──────────────────────────────────────────────────────────────────────────────
# Planner — uses sub-agents as tools to build a rich plan
# ──────────────────────────────────────────────────────────────────────────────

planner_agent = Agent[AgentContext](
    name='Planner',
    model='gpt-4o',
    instructions="""You create comprehensive social media campaign plans. Every post will have its image AI-generated using seed images, so every post MUST have seed images and an image generation prompt.

Follow these steps in order:

**Step 1 — Gather brand context**
Call get_brand_info and get_enabled_platforms.

**Step 2 — Design campaign structure**
Based on the user request and brand info, decide:
- Campaign title and theme
- Number of posts (3–7)
- For each post: topic, post_type (product/lifestyle/ad), target platforms

**Step 3 — Select seed images for every post**
You must use select_images tool and pass ALL post topics and types.
The Image Selector will always return at least one image per post.
Record the returned image_id(s) and image_url(s) for every post.

**Step 4 — Analyse the selected images**
Call analyse_selected_images, passing the list of selected images (id + url pairs for each post).
This gives you rich visual descriptions to inform the image generation prompts.

**Step 5 — Write image generation prompts for ALL posts**
Call write_image_prompts for ALL posts, providing:
- The post topic and type
- The visual description of the selected seed image(s) from step 4
Every post gets a generation prompt — the seed images guide the AI, the prompt directs the result.

**Step 6 — Output the complete plan as Markdown**

Use this exact structure:

---

# 📋 Campaign Plan: [Campaign Title]

**Theme:** [brief theme description]

---

## Posts

### Post 1: [Topic]
- **Platforms:** [comma-separated list]
- **Type:** [product / lifestyle / ad]
- **Seed Images** *(used to guide AI generation)*:
  - ID: 123 — ![](https://full-image-url.com/image.jpg)
- **Image Generation Prompt:**
  > [the generation prompt]

[repeat for every post]

---

> ✅ **Please review the plan and seed images above.**
> The seed images will guide the AI to generate styled images for each post.
> Reply **"approve"** to start creating posts, or describe any changes.

---

IMPORTANT:
- Always use `![](absolute_url)` so images render inline as thumbnails.
- Always show seed image IDs alongside the thumbnail.
- Every post must have at least one seed image AND a generation prompt.
""",
    tools=[
        get_brand_info,
        get_enabled_platforms,
        WebSearchTool(),
        image_selector_agent.as_tool(
            tool_name='select_images',
            tool_description=(
                'Select seed images for each campaign post from the media library or Unsplash. '
                'Every post is guaranteed to receive at least one image with a real DB integer ID and full URL. '
                'Pass all post topics and types at once.'
            ),
        ),
        image_analyser_agent.as_tool(
            tool_name='analyse_selected_images',
            tool_description=(
                'Analyse specific images that were already selected. '
                'Pass a list of {id, url} pairs for all selected images. '
                'Returns visual descriptions to inform image generation prompts.'
            ),
        ),
        image_prompt_writer_agent.as_tool(
            tool_name='write_image_prompts',
            tool_description=(
                'Write detailed AI image-generation prompts for all posts. '
                'For each post, provide: topic, post_type, and the visual description of its seed image(s). '
                'Returns one detailed prompt per post.'
            ),
        ),
    ],
)

# ──────────────────────────────────────────────────────────────────────────────
# Coordinator — entry point for all user interactions
# ──────────────────────────────────────────────────────────────────────────────

coordinator_agent = Agent[AgentContext](
    name='Coordinator',
    model='gpt-4o',
    instructions="""You are the campaign coordinator — the main agent users interact with.

## Workflow

**Step 1 — Planning (requires user approval)**
When a user requests a campaign, hand off to the Planner immediately.
The Planner will:
- Analyse the media library for available images
- Select the best existing images for each post
- Write generation prompts for posts without a suitable image
- Return a complete Markdown plan with inline image previews

Present the plan exactly as returned. Wait for the user to approve or request changes.
Do NOT proceed to post creation without explicit approval.

**Step 2 — Post Creation (fully autonomous, no further interruption)**
When the user approves (says "approve", "looks good", "go ahead", "yes", or similar):
- Hand off to Post Creator immediately.
- Post Creator works autonomously: generates missing images, writes all copy, creates all posts.
- Do NOT interrupt Post Creator. Do NOT ask for further confirmation.
- After it finishes, present its summary and confirm posts are in drafts.

## General Guidelines
- Be conversational and helpful.
- If the user wants changes to the plan, hand off to Planner again with the updated request.
- The only approval gate is after the plan is shown. Once approved, work runs to completion.
- Always use the brand's preferred language (from brand.language) for all communication, planning, and post copy.
""",
    tools=[get_brand_info, get_enabled_platforms],
    handoffs=[planner_agent, post_creator_agent],
)
