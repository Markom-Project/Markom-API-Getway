"""
MarKom PII Guardrail — CustomGuardrail for detecting and redacting PII in prompts and responses.

Runs on both pre_call (request) and post_call (response) phases.
"""

import json
import logging
import re
from typing import Any, Optional

from litellm.integrations.custom_guardrail import CustomGuardrail

logger = logging.getLogger("markom_gateway.pii_guardrail")


_DEFAULT_PATTERNS = [
    {
        "name": "email",
        "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "replacement": "[EMAIL_REDACTED]",
    },
    {
        "name": "phone_us",
        "pattern": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "replacement": "[PHONE_REDACTED]",
    },
    {
        "name": "ssn",
        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
        "replacement": "[SSN_REDACTED]",
    },
    {
        "name": "credit_card",
        "pattern": r"\b(?:\d[ -]*?){13,16}\b",
        "replacement": "[CARD_REDACTED]",
    },
    {
        "name": "ip_address",
        "pattern": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "replacement": "[IP_REDACTED]",
    },
    {
        "name": "aadhaar",
        "pattern": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
        "replacement": "[AADHAAR_REDACTED]",
    },
    {
        "name": "pan",
        "pattern": r"\b[A-Z]{5}\d{4}[A-Z]\b",
        "replacement": "[PAN_REDACTED]",
    },
]


class MarkomPIIGuardrail(CustomGuardrail):
    def __init__(
        self,
        redact_patterns: list[dict] = None,
        block_on_detection: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.block_on_detection = block_on_detection

        self.patterns = []
        if redact_patterns:
            for p in redact_patterns:
                self.patterns.append(
                    {
                        "name": p.get("name", "custom"),
                        "pattern": re.compile(p["pattern"]),
                        "replacement": f'[{p.get("name", "CUSTOM").upper()}_REDACTED]',
                    }
                )
        else:
            for p in _DEFAULT_PATTERNS:
                self.patterns.append(
                    {
                        **p,
                        "pattern": re.compile(p["pattern"]),
                    }
                )

    def _scan_text(self, text: str) -> list[dict]:
        findings = []
        for pat in self.patterns:
            matches = pat["pattern"].finditer(text)
            for match in matches:
                findings.append(
                    {
                        "type": pat["name"],
                        "start": match.start(),
                        "end": match.end(),
                        "value": match.group(),
                    }
                )
        return findings

    def _redact_text(self, text: str) -> tuple[str, list[dict]]:
        findings = self._scan_text(text)
        redacted = text
        for pat in self.patterns:
            redacted = pat["pattern"].sub(pat["replacement"], redacted)
        return redacted, findings

    def _redact_messages(self, messages: list) -> tuple[list, list[dict]]:
        all_findings = []
        redacted_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    redacted_content, findings = self._redact_text(content)
                    all_findings.extend(findings)
                    redacted_messages.append({**msg, "content": redacted_content})
                elif isinstance(content, list):
                    redacted_blocks = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            redacted_text, findings = self._redact_text(text)
                            all_findings.extend(findings)
                            redacted_blocks.append({**block, "text": redacted_text})
                        else:
                            redacted_blocks.append(block)
                    redacted_messages.append({**msg, "content": redacted_blocks})
                else:
                    redacted_messages.append(msg)
            else:
                redacted_messages.append(msg)
        return redacted_messages, all_findings

    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data: dict,
        call_type,
    ) -> Optional[dict]:
        messages = data.get("messages", [])
        if not messages:
            return data

        redacted_messages, findings = self._redact_messages(messages)
        if findings:
            logger.info(
                "PII detected in request: %d findings across %d types",
                len(findings),
                len(set(f["type"] for f in findings)),
            )
            if self.block_on_detection:
                from litellm.exceptions import GuardrailRegistrationException

                raise ValueError(
                    f"PII detected in request: {len(findings)} findings. "
                    f"Types: {list(set(f['type'] for f in findings))}"
                )
            data["messages"] = redacted_messages
            data.setdefault("metadata", {})["pii_findings"] = findings

        return data

    async def apply_guardrail(
        self,
        inputs,
        request_data: dict,
        input_type: str,
        logging_obj=None,
    ):
        if input_type == "request":
            texts = inputs.get("texts", [])
            all_findings = []
            redacted_texts = []
            for text in texts:
                redacted, findings = self._redact_text(text)
                redacted_texts.append(redacted)
                all_findings.extend(findings)
            inputs["texts"] = redacted_texts
            if all_findings:
                logger.info("PII detected in %s: %d findings", input_type, len(all_findings))
        return inputs
