import logging
import os
import shlex
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from media_library.models import ImageGroup
from services.video_poc import (
    ASPECT_RATIOS,
    DEFAULT_ASPECT_RATIO,
    MUAPI_MODEL_NAME,
    MUAPI_PROMPT_MAX_CHARS,
    MUAPI_SUBMIT_URL,
    VIDEO_TYPES,
    VISUAL_ANALYSIS_IMAGE_LIMIT,
    VideoPocError,
    analyze_product_visuals,
    build_briefs_prompt,
    build_group_context,
    build_keyframe_prompt,
    build_script_prompt,
    build_visual_analysis_prompt,
    copy_final_clip,
    download_file,
    generate_briefs,
    generate_script,
    get_run_dir,
    poll_muapi_clip,
    public_media_url,
    read_json,
    render_script,
    submit_muapi_clip,
    update_manifest,
    validate_script_payload,
    verify_public_url,
)
from services.ai_services import OpenAIModel


class Command(BaseCommand):
    help = 'Backend-only PoC for script-first single-clip video generation.'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', required=True)

        briefs = subparsers.add_parser('briefs', help='Generate 5 AI video briefs.')
        briefs.add_argument('--group-id', type=int, required=True)
        briefs.add_argument('--type', choices=VIDEO_TYPES, required=True)
        briefs.add_argument('--aspect-ratio', choices=ASPECT_RATIOS, default=DEFAULT_ASPECT_RATIO)
        briefs.add_argument('--run-id', default='')

        script = subparsers.add_parser('script', help='Generate an editable script from a selected brief.')
        script.add_argument('--briefs', required=True)
        script.add_argument('--brief-id', type=int, required=True)

        render = subparsers.add_parser('render', help='Generate Muapi payload and optional video clip.')
        render.add_argument('--script', required=True)
        render.add_argument('--submit-muapi', action='store_true')
        render.add_argument(
            '--create-keyframe',
            action='store_true',
            help='Generate a Gemini keyframe and include it as the first Muapi image reference.',
        )
        render.add_argument(
            '--regenerate-keyframes',
            action='store_true',
            help='With --create-keyframe, force a fresh keyframe instead of reusing an existing one.',
        )

        interactive = subparsers.add_parser('interactive', help='Run the video PoC as a console wizard.')
        interactive.add_argument('--group-id', type=int, required=True)
        interactive.add_argument('--type', choices=VIDEO_TYPES)
        interactive.add_argument('--aspect-ratio', choices=ASPECT_RATIOS)
        interactive.add_argument('--run-id', default='')
        interactive.add_argument('--submit-muapi', action='store_true')
        interactive.add_argument(
            '--create-keyframe',
            action='store_true',
            help='Generate a Gemini keyframe and include it as the first Muapi image reference.',
        )
        interactive.add_argument(
            '--regenerate-keyframes',
            action='store_true',
            help='With --create-keyframe, force a fresh keyframe instead of reusing an existing one.',
        )

    def handle(self, *args, **options):
        try:
            action = options['action']
            if action == 'briefs':
                output_path = generate_briefs(
                    group_id=options['group_id'],
                    video_type=options['type'],
                    aspect_ratio=options['aspect_ratio'],
                    run_id=options.get('run_id') or None,
                )
                self.stdout.write(self.style.SUCCESS(f'Generated briefs: {output_path}'))
                return

            if action == 'script':
                output_path = generate_script(
                    briefs_path=options['briefs'],
                    brief_id=options['brief_id'],
                )
                self.stdout.write(self.style.SUCCESS(f'Generated script: {output_path}'))
                return

            if action == 'render':
                manifest_path = render_script(
                    script_path=options['script'],
                    submit_muapi=options['submit_muapi'],
                    regenerate_keyframes=options['regenerate_keyframes'],
                    create_keyframe=options['create_keyframe'],
                )
                mode = 'real Muapi render' if options['submit_muapi'] else 'dry render'
                self.stdout.write(self.style.SUCCESS(f'Completed {mode}: {manifest_path}'))
                return

            if action == 'interactive':
                self._run_interactive(options)
                return

        except VideoPocError as exc:
            raise CommandError(str(exc)) from exc

    def _run_interactive(self, options):
        # Configure logging to show in interactive mode
        logger = logging.getLogger('services.video_poc')
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(handler)
        
        group = self._get_group(options['group_id'])
        self._print_group(group)

        video_type = options.get('type') or self._choose('Video type', VIDEO_TYPES, default='teaser')
        aspect_ratio = options.get('aspect_ratio') or DEFAULT_ASPECT_RATIO
        self.stdout.write(f'\nAspect ratio: {aspect_ratio}')
        run_id, run_dir = get_run_dir(options.get('run_id') or None)

        context = build_group_context(group)
        visual_images = list(group.images.all().order_by('id')[:VISUAL_ANALYSIS_IMAGE_LIMIT])
        if visual_images:
            self.stdout.write('\n>>> Analyzing product visuals...')
            visual_prompt = build_visual_analysis_prompt(context)
            self._print_prompt_trace(
                title='OpenAI visual analysis request',
                model=OpenAIModel.NORMAL.value,
                attachments=[
                    f'{image.id}: {image.external_url or (image.image.name if image.image else "")}'
                    for image in visual_images
                ],
                settings=[
                    'temperature: 0.2',
                    'max_tokens: 1600',
                    'response_format: json_object',
                ],
                prompt=visual_prompt,
            )
        visual_analysis = analyze_product_visuals(group, run_dir=run_dir)
        context['visual_analysis'] = visual_analysis
        self.stdout.write(self.style.SUCCESS(f'\nVisual analysis: {run_dir / "visual_analysis.json"}'))

        while True:
            self.stdout.write('\n>>> Generating briefs...')
            briefs_prompt = build_briefs_prompt(video_type, aspect_ratio, context)
            self._print_prompt_trace(
                title='OpenAI briefs request',
                model=OpenAIModel.NORMAL.value,
                attachments=['none'],
                settings=[
                    'temperature: 0.8',
                    'max_tokens: 3600',
                    'response_format: json_object',
                ],
                prompt=briefs_prompt,
            )
            briefs_path = generate_briefs(
                group_id=group.id,
                video_type=video_type,
                aspect_ratio=aspect_ratio,
                run_id=run_id,
                visual_analysis=visual_analysis,
            )
            briefs_payload = read_json(briefs_path)
            run_id = briefs_payload['run_id']
            self.stdout.write(self.style.SUCCESS(f'\nGenerated briefs: {briefs_path}'))
            self._print_briefs(briefs_payload)

            selected = self._prompt('\nChoose brief id, "r" to regenerate, or "q" to quit')
            if selected.lower() == 'q':
                self.stdout.write('Aborted.')
                return
            if selected.lower() == 'r':
                continue
            try:
                brief_id = int(selected)
            except ValueError:
                self.stderr.write('Enter a numeric brief id, "r", or "q".')
                continue
            if brief_id not in {int(brief['id']) for brief in briefs_payload.get('briefs', [])}:
                self.stderr.write(f'Brief id {brief_id} is not in this briefs file.')
                continue
            break

        brief = next(brief for brief in briefs_payload['briefs'] if int(brief['id']) == brief_id)
        self.stdout.write('\n>>> Generating script...')
        script_prompt = build_script_prompt(briefs_payload, brief)
        self._print_prompt_trace(
            title='OpenAI script request',
            model=OpenAIModel.NORMAL.value,
            attachments=['none'],
            settings=[
                'temperature: 0.65',
                'max_tokens: 3600',
                'response_format: json_object',
            ],
            prompt=script_prompt,
        )
        script_path = generate_script(briefs_path=briefs_path, brief_id=brief_id)
        self.stdout.write(self.style.SUCCESS(f'\nGenerated script: {script_path}'))
        self._review_script(script_path)

        self.stdout.write('\n>>> Rendering payload...')
        manifest_path = self._render_until_ready(
            script_path,
            regenerate_keyframes=options['regenerate_keyframes'],
            create_keyframe=options['create_keyframe'],
        )
        payload = self._review_render_outputs(manifest_path)

        should_submit = self._yes_no(
            '\nSubmit reviewed payload to Muapi now?',
            default=bool(options.get('submit_muapi')),
        )
        if not should_submit:
            self.stdout.write('Stopped after dry render.')
            return

        final_manifest_path = self._submit_reviewed_payload(manifest_path, payload)
        final_manifest = read_json(final_manifest_path)
        self.stdout.write(self.style.SUCCESS(f'\nCompleted Muapi render: {final_manifest_path}'))
        self.stdout.write(f"Final video: {final_manifest.get('final_video_path')}")
        if final_manifest.get('final_video_url'):
            self.stdout.write(f"Final URL: {final_manifest['final_video_url']}")

    def _get_group(self, group_id):
        try:
            return (
                ImageGroup.objects.select_related('project')
                .prefetch_related('images')
                .get(pk=group_id)
            )
        except ImageGroup.DoesNotExist as exc:
            raise VideoPocError(f'ImageGroup {group_id} was not found.') from exc

    def _print_group(self, group):
        description = (group.description or '').strip().replace('\n', ' ')
        if len(description) > 240:
            description = f'{description[:237]}...'
        self.stdout.write('\nSelected image group')
        self.stdout.write(f'ID: {group.id}')
        self.stdout.write(f'Project: {group.project_id} - {group.project.name}')
        self.stdout.write(f'Title: {group.title}')
        self.stdout.write(f'Type: {group.type}')
        self.stdout.write(f'Images: {len(group.images.all())}')
        if description:
            self.stdout.write(f'Description: {description}')

    def _print_briefs(self, briefs_payload):
        for brief in briefs_payload.get('briefs', []):
            self.stdout.write('')
            self.stdout.write(f"{brief['id']}. {brief.get('title', 'Untitled')}")
            self.stdout.write(f"Hook: {brief.get('hook', '')}")
            self.stdout.write(f"Story: {brief.get('story_angle', '')}")
            self.stdout.write(f"Proof: {brief.get('proof_mechanism', '')}")
            self.stdout.write(f"Visual hook: {brief.get('visual_hook', '')}")
            self.stdout.write(f"CTA: {brief.get('cta', '')}")

    def _review_script(self, script_path):
        try:
            payload = read_json(script_path)
            payload = validate_script_payload(payload)
        except (ValueError, VideoPocError) as exc:
            self.stderr.write(f'\nScript validation failed: {exc}')
            raise CommandError(f'Cannot proceed with invalid script: {exc}') from exc

        self._print_script_summary(payload)

    def _print_script_summary(self, payload):
        clip = payload['clip']
        self.stdout.write('\nScript summary')
        self.stdout.write(f"Video type: {payload.get('video_type')}")
        self.stdout.write(f"Aspect ratio: {payload.get('aspect_ratio')}")
        self.stdout.write(f"Duration: {clip['duration']}s")
        self.stdout.write('Beats:')
        for beat in clip.get('beats', []):
            self.stdout.write(
                f"- {beat['start_time']}-{beat['end_time']}s "
                f"({beat['duration_seconds']}s): {beat['visual_action']}"
            )
            self.stdout.write(f"  Camera: {beat['camera_motion']}")
            self.stdout.write(f"  Product focus: {beat['product_focus']}")
            self.stdout.write(f"  Transition: {beat['transition_to_next']}")
        self.stdout.write('Product rules:')
        for rule in clip.get('product_fidelity_rules', []):
            self.stdout.write(f'- {rule}')
        self.stdout.write('Framing rules:')
        for rule in clip.get('framing_rules', []):
            self.stdout.write(f'- {rule}')
        self.stdout.write('Negative rules:')
        for rule in clip.get('negative_rules', []):
            self.stdout.write(f'- {rule}')

    def _render_until_ready(self, script_path, regenerate_keyframes=False, create_keyframe=False):
        if not create_keyframe:
            manifest_path = render_script(
                script_path=script_path,
                submit_muapi=False,
                regenerate_keyframes=False,
                create_keyframe=False,
            )
            self.stdout.write(self.style.SUCCESS(f'\nDry render complete: {manifest_path}'))
            return manifest_path

        force_regenerate = regenerate_keyframes
        while True:
            self.stdout.write('\n>>> Generating keyframe...')
            self._print_keyframe_prompt(script_path)
            manifest_path = render_script(
                script_path=script_path,
                submit_muapi=False,
                regenerate_keyframes=force_regenerate,
                create_keyframe=True,
            )
            self.stdout.write(self.style.SUCCESS(f'\nDry render complete: {manifest_path}'))
            manifest = read_json(manifest_path)
            clip = manifest['clips'][0]
            self.stdout.write('\nKeyframe review')
            self.stdout.write(f"Keyframe: {clip['keyframe_path']}")
            self.stdout.write(f"Keyframe URL: {clip['keyframe_url']}")
            self.stdout.write(f"Source: {clip['keyframe_source']}")

            selected = self._prompt('Accept keyframe, "r" to regenerate, or "q" to quit', default='y')
            if selected.lower() in {'y', 'yes', 'accept', 'a'}:
                return manifest_path
            if selected.lower() == 'r':
                force_regenerate = True
                continue
            if selected.lower() == 'q':
                raise VideoPocError('Aborted after keyframe review.')
            self.stderr.write('Enter y, r, or q.')

    def _print_keyframe_prompt(self, script_path):
        script_payload = validate_script_payload(read_json(script_path))
        keyframe_prompt = build_keyframe_prompt(script_payload, script_payload['clip'])
        reference_images = script_payload.get('metadata', {}).get('reference_images', [])
        self._print_prompt_trace(
            title='Gemini keyframe request',
            model='gemini-3.1-flash-image-preview',
            attachments=[
                f"{image.get('id', '?')}: {image.get('source', '')}"
                for image in reference_images
            ] or ['none'],
            settings=[
                f"aspect_ratio: {script_payload.get('aspect_ratio')}",
                "response_modalities: IMAGE",
            ],
            prompt=keyframe_prompt,
        )

    def _review_render_outputs(self, manifest_path):
        manifest = read_json(manifest_path)
        clip = manifest['clips'][0]
        payload_path = Path(clip['muapi_payload_path'])
        keyframe_path = clip['keyframe_path']

        self.stdout.write('\nRender artifacts')
        if keyframe_path:
            self.stdout.write(f"Keyframe: {keyframe_path}")
            self.stdout.write(f"Keyframe URL: {clip['keyframe_url']}")
        else:
            self.stdout.write('Keyframe: disabled')
        self.stdout.write(f'Payload: {payload_path}')

        try:
            payload = read_json(payload_path)
        except ValueError as exc:
            raise VideoPocError(f'Payload JSON is invalid: {exc}') from exc

        if not isinstance(payload, dict) or not payload.get('prompt') or not payload.get('images_list'):
            raise VideoPocError('Payload must include "prompt" and "images_list".')

        prompt = payload.get('prompt', '')
        prompt_length = len(prompt)
        prompt_status = '✓ OK' if prompt_length <= MUAPI_PROMPT_MAX_CHARS else '✗ OVER LIMIT'
        self.stdout.write(f'\nPrompt check: {prompt_length}/{MUAPI_PROMPT_MAX_CHARS} chars {prompt_status}')
        if prompt_length > MUAPI_PROMPT_MAX_CHARS:
            self.stderr.write(
                f'ERROR: Prompt is {prompt_length - MUAPI_PROMPT_MAX_CHARS} characters over the Muapi limit. '
                f'This payload cannot be submitted.'
            )

        self._print_prompt_trace(
            title='Muapi Seedance request',
            model=MUAPI_MODEL_NAME,
            attachments=payload.get('images_list') or ['none'],
            settings=[
                f"endpoint: {MUAPI_SUBMIT_URL}",
                f"aspect_ratio: {payload.get('aspect_ratio')}",
                f"duration: {payload.get('duration')}",
                f"prompt_length: {prompt_length}/{MUAPI_PROMPT_MAX_CHARS}",
            ],
            prompt=prompt,
        )
        return payload

    def _submit_reviewed_payload(self, manifest_path, payload):
        manifest_path = Path(manifest_path)
        run_dir = manifest_path.parent
        manifest = read_json(manifest_path)
        clip = manifest['clips'][0]

        prompt_length = len(payload.get('prompt', ''))
        if prompt_length > MUAPI_PROMPT_MAX_CHARS:
            raise VideoPocError(
                f'Cannot submit: prompt is {prompt_length} chars (limit is {MUAPI_PROMPT_MAX_CHARS}). '
                f'{prompt_length - MUAPI_PROMPT_MAX_CHARS} characters over limit.'
            )

        if clip.get('keyframe_url'):
            verify_public_url(clip['keyframe_url'])
        self.stdout.write('\n>>> Submitting to Muapi...')
        request_id, submit_response = submit_muapi_clip(payload)
        self.stdout.write(f'Muapi request ID: {request_id}')
        self.stdout.write('>>> Polling for video generation...')
        output_url, result_response = poll_muapi_clip(request_id)

        self.stdout.write('>>> Downloading video...')
        clip_path = run_dir / 'clips' / 'clip_01.mp4'
        download_file(output_url, clip_path)
        final_path = copy_final_clip(clip_path, run_dir / 'final.mp4')

        clip.update({
            'status': 'completed',
            'muapi_request_id': request_id,
            'muapi_submit_response': submit_response,
            'muapi_result_response': result_response,
            'muapi_output_url': output_url,
            'clip_path': str(clip_path),
            'muapi_payload': payload,
        })
        manifest.update({
            'status': 'completed',
            'submit_muapi': True,
            'clips': [clip],
            'final_video_path': str(final_path),
            'final_video_url': public_media_url(final_path),
        })
        return update_manifest(run_dir, manifest)

    def _choose(self, label, choices, default):
        choices = tuple(choices)
        self.stdout.write(f'\n{label}')
        for index, choice in enumerate(choices, 1):
            marker = ' default' if choice == default else ''
            self.stdout.write(f'{index}. {choice}{marker}')

        while True:
            answer = self._prompt(f'Choose {label.lower()}', default=default)
            if answer in choices:
                return answer
            try:
                selected = choices[int(answer) - 1]
            except (ValueError, IndexError):
                self.stderr.write(f'Choose one of: {", ".join(choices)}')
                continue
            return selected

    def _yes_no(self, question, default=False):
        suffix = '[Y/n]' if default else '[y/N]'
        while True:
            answer = self._prompt(f'{question} {suffix}').lower()
            if not answer:
                return default
            if answer in {'y', 'yes'}:
                return True
            if answer in {'n', 'no'}:
                return False
            self.stderr.write('Enter y or n.')

    def _prompt(self, question, default=''):
        suffix = f' [{default}]' if default else ''
        try:
            answer = input(f'{question}{suffix}: ').strip()
        except EOFError:
            answer = ''
        return answer or default

    def _open_editor(self, path):
        editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
        if not editor:
            self.stdout.write(f'Edit this file if needed, then press Enter: {path}')
            self._prompt('Continue')
            return

        command = shlex.split(editor) + [str(path)]
        try:
            subprocess.run(command, check=False)
        except FileNotFoundError:
            self.stderr.write(f'Editor not found: {editor}')
            self.stdout.write(f'Edit this file if needed, then press Enter: {path}')
            self._prompt('Continue')

    def _print_prompt_trace(self, title, model, attachments, settings, prompt):
        self.stdout.write(f'\n=== {title} ===')
        self.stdout.write(f'Model: {model}')
        self.stdout.write('Settings:')
        for item in settings:
            self.stdout.write(f'- {item}')
        self.stdout.write('Attachments:')
        for item in attachments:
            self.stdout.write(f'- {item}')
        self.stdout.write(f'Prompt length: {len(prompt or "")} chars')
        self.stdout.write('Prompt:')
        self.stdout.write(prompt or '')
        self.stdout.write(f'=== End {title} ===')
