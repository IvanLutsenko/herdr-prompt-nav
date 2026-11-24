#!/bin/sh
# Open the prompt list as a popup over the active pane; herdr always places popups there.
exec "${HERDR_BIN_PATH:-herdr}" plugin pane open --plugin "${HERDR_PLUGIN_ID:-ivanlutsenko.prompt-nav}" \
    --entrypoint prompts --placement popup --env NAV_TARGET="$HERDR_PANE_ID" --width 80% --height 70% --focus
