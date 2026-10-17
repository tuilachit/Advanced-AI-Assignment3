"""Task 3 inspection harness: preserve allowlisted service output, never SDK objects."""
import json
import sys
from collections import Counter
from pathlib import Path

import run_live_evaluation as runner
from app.providers.openai_provider import (
    AGENT_INSTRUCTIONS,
    CV_GENERATION_INSTRUCTIONS,
    CV_VALIDATION_INSTRUCTIONS,
)
from app.services.live_evaluation import _contains_sensitive_text


def main():
    scenario, destination = sys.argv[1:3]
    selected_profiles = sys.argv[3:]
    if selected_profiles:
        original_profiles = runner._profiles_by_id()
        runner._profiles_by_id = lambda: {key: original_profiles[key] for key in selected_profiles}
    output = Path(destination)
    counts = Counter()
    events = []
    services = runner._build_live_services()

    def wrap(obj, method, event_name, capture):
        original = getattr(obj, method)

        def observed(*args, **kwargs):
            counts[event_name] += 1
            result = original(*args, **kwargs)
            events.append({'type': event_name, **capture(args, kwargs, result)})
            return result

        setattr(obj, method, observed)

    provider = services.agent_provider
    wrap(provider, 'generate_cv', 'generate_cv', lambda args, kw, result: {
        'profile': args[0].model_dump(mode='json'),
        'target_job_id': args[1].document_id,
        'cv': result.model_dump(mode='json'),
    })
    wrap(provider, 'validate_claims', 'validate_claims', lambda args, kw, result: {
        'target_job_id': args[0].target_job_id,
        'issues': [item.model_dump(mode='json') for item in result],
    })
    wrap(provider, 'respond', 'respond', lambda args, kw, result: {
        'message': result.message,
        'actions': [{'name': call.name, 'arguments': call.arguments} for call in result.tool_calls],
    })
    wrap(services.retrieval._embedder, 'embed', 'embed', lambda args, kw, result: {
        'input_count': len(args[0]),
        'query': args[0][0] if len(args[0]) == 1 else None,
    })
    wrap(services.agent, 'handle_message', 'agent_turn', lambda args, kw, result: {
        'message': result.message,
        'observations': [item.model_dump(mode='json') for item in result.observations],
        'profile': services.workflow.get_session(args[0]).profile.model_dump(mode='json'),
    })
    try:
        code = runner.main(['--scenario', scenario, '--output-dir', destination], services_factory=lambda: services)
    except Exception:
        # Do not print exception text: it may contain unredacted provider details.
        code = 2
        events.append({'type': 'harness_failure', 'message': 'Unhandled error; details suppressed.'})
    supplement = {
        'scenario': scenario,
        'selected_profiles': selected_profiles,
        'model_configuration': runner.MODEL_CONFIGURATION.model_dump(),
        'prompts': {'agent': AGENT_INSTRUCTIONS, 'generation': CV_GENERATION_INSTRUCTIONS, 'validation': CV_VALIDATION_INSTRUCTIONS},
        'logical_provider_calls': {key: counts[key] for key in ('embed', 'respond', 'generate_cv', 'validate_claims')},
        'events': events,
        'runner_exit_code': code,
    }
    if _contains_sensitive_text(supplement):
        print('Supplement rejected by secret scan; contents suppressed.')
        return 3
    output.mkdir(parents=True, exist_ok=True)
    (output / 'service-evidence.json').write_text(json.dumps(supplement, indent=2) + '\n')
    print(json.dumps({'scenario': scenario, 'exit_code': code, 'logical_provider_calls': supplement['logical_provider_calls'], 'supplement_scan': 'passed'}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
