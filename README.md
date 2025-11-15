Based on [https://github.com/openai/codex/blob/main/docs/config.md#notify](https://github.com/openai/codex/blob/main/docs/config.md#notify)

## Installation

Pre-requisite:
```
brew install terminal-notifier
```

Add to `~/.codex/config.toml` at the top level (before `[...]` blocks):

```
notify = ["python3", "/<path>/notify.py"]
```
