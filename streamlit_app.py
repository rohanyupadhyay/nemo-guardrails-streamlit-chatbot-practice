import html
import os

import streamlit as st
from dotenv import load_dotenv

from guardrail_checks import (
    GuardrailEvent,
    GuardrailSettings,
    evaluate_input,
    evaluate_output,
    first_block,
    safe_answer_context,
)
from guardrails_config import build_cheese_rails
from test_prompts import TEST_PROMPTS

load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
openai_model = os.getenv("OPENAI_MODEL")
MAX_HISTORY_MESSAGES = 12


def get_cheese_rails(model: str, topic_guardrail: bool, output_guardrail: bool):
    return build_cheese_rails(model, topic_guardrail, output_guardrail)


def get_response_content(response) -> str:
    # Newer NeMo versions return a GenerationResponse object. Some examples in
    # the docs show a plain dict, so this helper supports both shapes.
    content = response["content"] if isinstance(response, dict) else response.response
    if isinstance(content, list):
        return "\n".join(message.get("content", "") for message in content)
    return content


def render_events(events: list[GuardrailEvent]) -> None:
    if not events:
        st.caption("No deterministic guardrail events.")
        return

    for event in events:
        if event.action == "block":
            st.error(f"{event.name}: {event.reason}")
        elif event.action == "warn":
            st.warning(f"{event.name}: {event.reason}")
        else:
            st.info(f"{event.name}: {event.reason}")


def settings_from_sidebar() -> tuple[GuardrailSettings, bool, bool]:
    with st.sidebar:
        st.header("Guardrails Lab")
        strictness = st.segmented_control(
            "Topic strictness",
            ["Strict", "Loose"],
            default="Strict",
            help="Loose mode allows broader dairy and food-prep prompts before NeMo checks them.",
        ) or "Strict"
        max_prompt_chars = st.slider("Max prompt characters", 200, 4000, 1200, 100)

        st.subheader("Checks")
        topic_guardrail = st.checkbox("Topic guardrail", value=True)
        prompt_injection_guardrail = st.checkbox("Prompt injection", value=True)
        pii_guardrail = st.checkbox("PII/secrets", value=True)
        food_safety_guardrail = st.checkbox("Food safety", value=True)
        medical_boundary_guardrail = st.checkbox("Medical boundary", value=True)
        output_guardrail = st.checkbox("Output rail", value=True)

        st.subheader("Practice")
        debug_mode = st.checkbox("Debug mode", value=True)
        show_test_prompts = st.checkbox("Show test prompts", value=True)

    return (
        GuardrailSettings(
            max_prompt_chars=max_prompt_chars,
            topic_guardrail=topic_guardrail,
            prompt_injection_guardrail=prompt_injection_guardrail,
            pii_guardrail=pii_guardrail,
            food_safety_guardrail=food_safety_guardrail,
            medical_boundary_guardrail=medical_boundary_guardrail,
            output_guardrail=output_guardrail,
            strictness=strictness,
        ),
        debug_mode,
        show_test_prompts,
    )


def render_test_prompts() -> None:
    with st.expander("Practice prompts", expanded=False):
        st.iframe(_copyable_prompts_html(TEST_PROMPTS), height=720)


def _copyable_prompts_html(prompts: list[dict]) -> str:
    rows = []
    for index, item in enumerate(prompts):
        prompt = str(item["prompt"])
        label = html.escape(str(item["label"]))
        expected = html.escape(str(item["expected"]))
        prompt_html = html.escape(prompt)
        prompt_attr = html.escape(prompt, quote=True)
        rows.append(
            f"""
            <section class="prompt-card">
              <div class="prompt-meta">
                <strong>{label}</strong>
                <span>Expected: {expected}</span>
              </div>
              <pre id="prompt-{index}">{prompt_html}</pre>
              <div class="prompt-actions">
                <button type="button" data-prompt="{prompt_attr}" data-index="{index}">
                  Copy prompt
                </button>
                <span id="copy-status-{index}" aria-live="polite"></span>
              </div>
            </section>
            """
        )

    return f"""
<!doctype html>
<html>
  <head>
    <style>
      :root {{
        color-scheme: dark;
        font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      body {{
        margin: 0;
        padding: 0 2px 8px;
        background: transparent;
        color: #f7f7f8;
      }}
      .prompt-card {{
        border: 1px solid rgba(250, 250, 250, 0.18);
        border-radius: 8px;
        padding: 12px;
        margin: 0 0 12px;
        background: rgba(255, 255, 255, 0.035);
      }}
      .prompt-meta {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px 12px;
        align-items: baseline;
        margin-bottom: 8px;
      }}
      .prompt-meta strong {{
        font-size: 14px;
        line-height: 20px;
      }}
      .prompt-meta span {{
        color: rgba(250, 250, 250, 0.68);
        font-size: 13px;
        line-height: 18px;
      }}
      pre {{
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        margin: 0;
        padding: 10px;
        border-radius: 6px;
        background: rgba(0, 0, 0, 0.25);
        color: #f7f7f8;
        font-family: "Roboto Mono", "SFMono-Regular", Consolas, monospace;
        font-size: 13px;
        line-height: 19px;
      }}
      .prompt-actions {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 10px;
        min-height: 34px;
      }}
      button {{
        appearance: none;
        border: 1px solid #ff4b4b;
        border-radius: 6px;
        padding: 7px 10px;
        background: #ff4b4b;
        color: white;
        font: inherit;
        font-size: 13px;
        line-height: 18px;
        cursor: pointer;
      }}
      button:hover {{
        background: #ff6b6b;
        border-color: #ff6b6b;
      }}
      button:focus-visible {{
        outline: 2px solid white;
        outline-offset: 2px;
      }}
      .prompt-actions span {{
        color: rgba(250, 250, 250, 0.72);
        font-size: 13px;
      }}
    </style>
  </head>
  <body>
    {''.join(rows)}
    <script>
      async function copyPrompt(button) {{
        const text = button.dataset.prompt;
        const status = document.getElementById(`copy-status-${{button.dataset.index}}`);

        try {{
          if (window.parent && window.parent.navigator && window.parent.navigator.clipboard) {{
            await window.parent.navigator.clipboard.writeText(text);
          }} else if (navigator.clipboard && window.isSecureContext) {{
            await navigator.clipboard.writeText(text);
          }} else {{
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.left = "-9999px";
            document.body.appendChild(textarea);
            textarea.select();
            const copied = document.execCommand("copy");
            document.body.removeChild(textarea);
            if (!copied) {{
              throw new Error("Copy command failed");
            }}
          }}
          status.textContent = "Copied";
          button.textContent = "Copied";
          window.setTimeout(() => {{
            status.textContent = "";
            button.textContent = "Copy prompt";
          }}, 1600);
        }} catch (error) {{
          status.textContent = "Copy failed";
          button.textContent = "Copy failed";
        }}
      }}

      document.querySelectorAll("button[data-prompt]").forEach((button) => {{
        button.addEventListener("click", () => copyPrompt(button));
      }});
    </script>
  </body>
</html>
"""


def trim_history(messages: list[dict]) -> list[dict]:
    return messages[-MAX_HISTORY_MESSAGES:]


st.title("Cheese Chatbot")
st.write(
    "Practice topical, injection, PII, food-safety, medical-boundary, and output guardrails."
)

settings, debug_mode, show_test_prompts = settings_from_sidebar()
if show_test_prompts:
    render_test_prompts()

if not openai_api_key:
    st.info("Please add OPENAI_API_KEY to your .env file to continue.", icon="🗝️")
elif not openai_model:
    st.info("Please add OPENAI_MODEL to your .env file to continue.", icon="⚙️")
else:

    cheese_rails = get_cheese_rails(
        openai_model,
        settings.topic_guardrail,
        settings.output_guardrail,
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask a cheese question"):
        with st.chat_message("user"):
            st.markdown(prompt)

        input_events = evaluate_input(prompt, settings)
        input_block = first_block(input_events)

        if debug_mode:
            with st.expander("Input guardrail trace", expanded=True):
                render_events(input_events)

        if input_block:
            with st.chat_message("assistant"):
                st.markdown(input_block.message)
            st.stop()

        if settings.topic_guardrail:
            with st.spinner("Checking NeMo topic policy..."):
                input_check = cheese_rails.generate(
                    messages=[{"role": "user", "content": prompt}],
                    options={"rails": ["input"]},
                )

            input_check_content = get_response_content(input_check)
            if input_check_content.strip() != prompt.strip():
                if debug_mode:
                    with st.expander("NeMo input rail", expanded=True):
                        st.error("NeMo blocked this prompt.")
                        st.write(input_check_content)
                with st.chat_message("assistant"):
                    st.markdown(input_check_content)
                st.stop()

        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.messages = trim_history(st.session_state.messages)

        guidance = safe_answer_context(input_events)
        model_messages = list(st.session_state.messages)
        if guidance:
            model_messages.insert(
                -1,
                {
                    "role": "system",
                    "content": "Additional guardrail guidance for this turn:\n" + guidance,
                },
            )

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                rails_response = cheese_rails.generate(messages=model_messages)
            response = get_response_content(rails_response)

            output_events = evaluate_output(response, settings)
            output_block = first_block(output_events)
            if debug_mode:
                with st.expander("Output guardrail trace", expanded=True):
                    render_events(output_events)

            if output_block:
                response = output_block.message

            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.messages = trim_history(st.session_state.messages)
