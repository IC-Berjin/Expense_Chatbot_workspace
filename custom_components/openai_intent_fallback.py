from __future__ import annotations

import os
import json
import requests
from typing import Any, Dict, List, Text

from rasa.engine.graph import GraphComponent, ExecutionContext
from rasa.engine.storage.resource import Resource
from rasa.engine.storage.storage import ModelStorage
from rasa.engine.recipes.default_recipe import DefaultV1Recipe
from rasa.shared.nlu.training_data.message import Message


AVAILABLE_INTENTS = [
    "greet",
    "goodbye",
    "mood_great",
    "mood_unhappy",
    "bot_challenge",

    "ask_employee_attribute",
    "ask_employee_by_name",
    "ask_employee_by_email",
    "ask_employee_by_code",
    "list_employees",
    "ask_employee_manager",
    "ask_my_employee_details",
    "ask_my_employee_attribute",

    "ask_employee_expense_claims",
    "ask_expense_claim_attribute",
    "ask_expense_claim_attribute_email",
    "ask_expense_claims",
    "ask_employee_expense_claims_email",
    "ask_expense_claim_status",
    "ask_expense_payment_status",

    "ask_my_expense_claims",
    "ask_my_expense_claim_attribute",
    "ask_my_expense_item_claims",
    "ask_my_expense_claim_status",
    "ask_my_expense_payment_status",
    "ask_my_expense_claim_summary",
    "ask_my_expense_claim_count",
    "ask_my_expense_claim_average",
    "ask_my_expense_claim_comparison",

    "ask_expense_item_claims",
    "ask_expense_claim_summary",
    "ask_expense_claim_count",
    "ask_expense_claim_average",
    "ask_expense_claim_comparison",
    "ask_expense_claim_top_analysis",

    "rag_policy_question",
    "rag_rebuild",
    "help",
]

AVAILABLE_ENTITIES = [
    "employee_name",
    "employee_code",
    "employee_email",
    "employee_field",
    "expense_claim_field",
    "expense_status",
    "payment_status",
    "expense_category",
    "policy_name",
    "department",
    "branch",
]


@DefaultV1Recipe.register(
    DefaultV1Recipe.ComponentType.INTENT_CLASSIFIER,
    is_trainable=False,
)
class OpenAIIntentFallback(GraphComponent):
    def __init__(self, config: Dict[Text, Any]) -> None:
        self.config = config
        self.threshold = config.get("threshold", 0.65)
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.model = config.get("model", "gpt-4o-mini")

    @classmethod
    def create(
        cls,
        config: Dict[Text, Any],
        model_storage: ModelStorage,
        resource: Resource,
        execution_context: ExecutionContext,
    ) -> "OpenAIIntentFallback":
        return cls(config)

    def process(self, messages: List[Message]) -> List[Message]:

        print(f"OpenAIIntentFallback initialized")

        for message in messages:
            current_intent = message.get("intent") or {}
            current_confidence = current_intent.get("confidence", 0.0)

            # Do not touch good Rasa predictions
            if current_confidence >= self.threshold:
                continue

            text = message.get("text")
            if not text:
                continue

            openai_result = self._classify_with_openai(text)

            if not openai_result:
                continue

            intent_name = openai_result.get("intent")
            confidence = float(openai_result.get("confidence", 0.0))

            if intent_name not in AVAILABLE_INTENTS:
                continue

            if confidence < self.threshold:
                continue

            entities = self._convert_entities(openai_result.get("entities", []))

            message.set(
                "intent",
                {
                    "name": intent_name,
                    "confidence": confidence,
                },
                add_to_output=True,
            )

            message.set(
                "intent_ranking",
                [
                    {
                        "name": intent_name,
                        "confidence": confidence,
                    }
                ],
                add_to_output=True,
            )

            message.set(
                "entities",
                entities,
                add_to_output=True,
            )

        return messages

    def _classify_with_openai(self, user_text: str) -> Dict[str, Any] | None:
        if not self.openai_api_key:
            return None

        prompt = f"""
You are an intent and entity classifier for a Rasa chatbot.

You must select only one intent from this list:
{json.dumps(AVAILABLE_INTENTS, indent=2)}

You can extract only these entities:
{json.dumps(AVAILABLE_ENTITIES, indent=2)}

User message:
{user_text}

Return only valid JSON in this format:
{{
  "intent": "intent_name",
  "confidence": 0.0,
  "entities": [
    {{
      "entity": "entity_name",
      "value": "entity_value"
    }}
  ]
}}

Rules:
1. Do not invent intent names.
2. Do not invent entity names.
3. If the message is about company policy, reimbursement policy, travel policy, or HR policy, use rag_policy_question.
4. If the user asks about their own details, use ask_my_employee_details or ask_my_employee_attribute.
5. If the user asks about another employee by name/email/code, use the relevant employee intent.
6. If the user asks about expense claims, payment status, claim summary, count, average, comparison, or top analysis, use the matching expense intent.
7. If not clear, return confidence below 0.50.
"""

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You return only valid JSON. No explanation.",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    "temperature": 0,
                },
                timeout=10,
            )

            response.raise_for_status()

            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)

        except Exception:
            return None

    def _convert_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rasa_entities = []

        for entity in entities:
            entity_name = entity.get("entity")
            value = entity.get("value")

            if entity_name not in AVAILABLE_ENTITIES:
                continue

            if value in [None, ""]:
                continue

            rasa_entities.append(
                {
                    "entity": entity_name,
                    "value": value,
                    "confidence_entity": 0.90,
                    "extractor": "OpenAIIntentFallback",
                }
            )

        return rasa_entities