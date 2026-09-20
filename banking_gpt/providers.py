from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from ollama import chat
from pydantic import ValidationError

from banking_gpt.models import (
    ActionType,
    Goal,
    Locator,
    LocatorStrategy,
    Observation,
    ProposedAction,
)


class DiscoveryModel(ABC):
    @abstractmethod
    async def decide(
        self,
        goal: Goal,
        observation: Observation,
        history: list[ProposedAction],
    ) -> ProposedAction: ...


class ScriptedDiscoveryModel(DiscoveryModel):
    """Offline provider for development only; it is not submission evidence."""

    def __init__(self, member_id: str) -> None:
        self.member_id = member_id

    async def decide(
        self,
        goal: Goal,
        observation: Observation,
        history: list[ProposedAction],
    ) -> ProposedAction:
        on_search_page = "Member Search" in observation.visible_text
        on_details_page = "Member Details" in observation.visible_text
        if on_search_page and not on_details_page:
            if not history:
                return ProposedAction(
                    action=ActionType.FILL,
                    target=[Locator(strategy=LocatorStrategy.LABEL, value="Member ID")],
                    value=self.member_id,
                    output_name=None,
                    explanation="Enter the requested member ID",
                )
            return ProposedAction(
                action=ActionType.CLICK,
                target=[Locator(strategy=LocatorStrategy.ROLE, value="button", name="Search")],
                value=None,
                output_name=None,
                explanation="Submit the member search",
            )
        if "Member not found" in observation.visible_text:
            return ProposedAction(
                action=ActionType.COMPLETE,
                target=[],
                value=None,
                output_name=None,
                explanation="The application returned a member-not-found business outcome",
            )
        if "Member Details" in observation.visible_text and not any(
            action.action == ActionType.EXTRACT for action in history
        ):
            return ProposedAction(
                action=ActionType.EXTRACT,
                target=[Locator(strategy=LocatorStrategy.TEST_ID, value="checking-balance")],
                value=None,
                output_name="balance",
                explanation="Extract the checking-account balance",
            )
        return ProposedAction(
            action=ActionType.COMPLETE,
            target=[],
            value=None,
            output_name=None,
            explanation="The requested balance has been extracted",
        )


class OllamaDiscoveryModel(DiscoveryModel):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def decide(
        self,
        goal: Goal,
        observation: Observation,
        history: list[ProposedAction],
    ) -> ProposedAction:
        prompt = f"""You operate a browser through a safe action interface.
Choose exactly one next action that advances the goal.
Only target controls present in the observation. Prefer label, role, text, then test_id.
Use extract with output_name='balance' for the requested balance.
Use complete only after extraction or a clear business outcome.
Every click, fill, extract, and verify action MUST include at least one target locator.
For a role locator, set value to the role (for example "button") and name to its visible name.
For a label locator, set value to the exact visible field label.
For complete, use an empty target list.

Valid fill example:
{{
  "action":"fill",
  "target":[{{"strategy":"label","value":"Member ID","priority":1}}],
  "value":"12345",
  "output_name":null,
  "explanation":"Enter member ID"
}}

Valid click example:
{{
  "action":"click",
  "target":[{{"strategy":"role","value":"button","name":"Search","priority":1}}],
  "value":null,
  "output_name":null,
  "explanation":"Submit search"
}}

Goal:
{goal.description}

Observation:
{observation.model_dump_json(indent=2)}

Previous actions:
{[item.model_dump(mode='json') for item in history]}
"""

        def invoke() -> ProposedAction:
            message: dict[str, object] = {"role": "user", "content": prompt}
            if observation.screenshot_path:
                message["images"] = [observation.screenshot_path]
            messages = [message]
            last_error: ValidationError | None = None
            for _ in range(3):
                response = chat(
                    model=self.model_name,
                    messages=messages,
                    format=ProposedAction.model_json_schema(),
                    options={"temperature": 0},
                )
                try:
                    return ProposedAction.model_validate_json(response.message.content)
                except ValidationError as exc:
                    last_error = exc
                    messages.append(response.message)
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your action failed validation. Correct it using only controls "
                                f"from the observation. Validation error: {exc}"
                            ),
                        }
                    )
            assert last_error is not None
            raise last_error

        return await asyncio.to_thread(invoke)
