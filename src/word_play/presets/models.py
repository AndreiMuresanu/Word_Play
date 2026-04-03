from __future__ import annotations

import os
from typing import Callable

from word_play.model import Model


class OpenRouter_Model(Model):
    """
    Chat model backed by OpenRouter.

    Example model names:
        - "meta-llama/llama-3.1-8b-instruct"
        - "openai/gpt-4o"
        - "anthropic/claude-3-5-sonnet"
        - "google/gemma-3-1b-it:free"

    Requires the OPENROUTER_API_KEY environment variable to be set.
    """

    _CLIENT = None

    def __init__(
        self,
        model_name: str,
        system_prompt: str = "",
        generation_params: dict | None = None,
        site_url: str | None = None,
        app_name: str | None = None,
        verbosity: int = 0,
    ):
        super().__init__(verbosity=verbosity)
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.generation_params = generation_params or {}

        headers = {}
        if site_url:
            headers["HTTP-Referer"] = site_url
        if app_name:
            headers["X-Title"] = app_name
        self._headers = headers

    def _get_client(self):
        if OpenRouter_Model._CLIENT is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ImportError("OpenRouter_Model requires the 'openai' package.") from exc

            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise EnvironmentError("Missing environment variable: OPENROUTER_API_KEY")

            OpenRouter_Model._CLIENT = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers=self._headers or None,
            )
        return OpenRouter_Model._CLIENT

    def generate_text(self, input_text: str | list[str], generation_config=None, max_new_tokens=None) -> str:
        if isinstance(input_text, list):
            raise NotImplementedError("Batched input is not supported.")

        params = {**self.generation_params, **(generation_config or {})}
        if max_new_tokens is not None:
            params["max_tokens"] = max_new_tokens

        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": input_text})

        response = self._get_client().chat.completions.create(
            model=self.model_name,
            messages=messages,
            **params,
        )
        return response.choices[0].message.content.strip()


class Human_Model(Model):
    def generate_text(self, input_text, generation_config=None, max_new_tokens=None):
        return input(
            f"""
========================= input START =========================
{input_text}
HUMAN input: """
        )


class Lazy_Model_Handle(Model):
    """
    Defers model construction until the first generate_text call.
    """

    def __init__(self, loader: Callable[[], Model], verbosity: int = 0):
        super().__init__(verbosity=verbosity)
        self.loader = loader
        self._model: Model | None = None

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = self.loader()
        return self._model

    def generate_text(self, input_text: str | list[str], generation_config=None, max_new_tokens=None) -> str:
        if max_new_tokens is None:
            return self.model.generate_text(
                input_text,
                generation_config=generation_config,
            )

        try:
            return self.model.generate_text(
                input_text,
                generation_config=generation_config,
                max_new_tokens=max_new_tokens,
            )
        except TypeError as exc:
            if "max_new_tokens" not in str(exc):
                raise
            return self.model.generate_text(
                input_text,
                generation_config=generation_config,
            )

    def cond_logP(self, inputs, targets):
        return self.model.cond_logP(inputs, targets)


LLM_MODEL_REGISTRY: dict[str, Model] = {}


def resolve_registered_model(model_key: str) -> Model:
    if model_key not in LLM_MODEL_REGISTRY:
        raise KeyError(
            f"Model '{model_key}' not found in LLM_MODEL_REGISTRY. "
            f"Available keys: {list(LLM_MODEL_REGISTRY)}"
        )
    return LLM_MODEL_REGISTRY[model_key]
