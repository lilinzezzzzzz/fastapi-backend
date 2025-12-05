import time
from typing import Any, AsyncGenerator, NamedTuple

import openai
from openai import NOT_GIVEN
from openai.types.chat import (
    ChatCompletion, ChatCompletionAssistantMessageParam, ChatCompletionDeveloperMessageParam,
    ChatCompletionFunctionMessageParam, ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam, ChatCompletionUserMessageParam
)

from pkg.logger_tool import logger


class ChatCompletionRes(NamedTuple):
    start_at: int
    end_at: int
    chat_completion: ChatCompletion | None = None
    error: str | dict | None = None


class OpenAIClient:
    def __init__(self, base_url: str, model: str, timeout: int = 180, api_key: str = "password"):
        self.model = model
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    @staticmethod
    def _convert_messages(
            messages: list[dict[str, Any]]
    ) -> list[ChatCompletionMessageParam]:
        """统一将 messages 转换为符合 OpenAI SDK 的格式"""
        if not messages:
            return []

        converted: list[ChatCompletionMessageParam] = []
        for i, msg in enumerate(messages):
            role = msg.get("role")
            content = msg.get("content")

            if not role:
                raise ValueError(f"Invalid message[{i}] missing role: {msg}")

            # 根据 role 构造具体的 Param 类型
            if role == "user":
                converted.append(ChatCompletionUserMessageParam(role="user", content=content))
            elif role == "system":
                converted.append(ChatCompletionSystemMessageParam(role="system", content=content))
            elif role == "assistant":
                converted.append(ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=content,
                    tool_calls=msg.get("tool_calls"),
                    function_call=msg.get("function_call"),
                    refusal=msg.get("refusal"),
                    audio=msg.get("audio"),
                ))
            elif role == "developer":
                converted.append(ChatCompletionDeveloperMessageParam(
                    role="developer",
                    content=content,
                    name=msg.get("name"),
                ))
            elif role == "tool":
                converted.append(ChatCompletionToolMessageParam(
                    role="tool",
                    content=content,
                    tool_call_id=msg.get("tool_call_id"),
                ))
            elif role == "function":
                converted.append(ChatCompletionFunctionMessageParam(
                    role="function",
                    content=content,
                    name=msg.get("name"),
                ))
            else:
                raise ValueError(f"Invalid role '{role}' at message[{i}]")

        return converted

    async def chat_completion(
            self,
            *,
            messages: list[dict[str, Any]],
            max_tokens: int | None = None,
            temperature: float | None = None,
            top_p: float | None = None,
            n: int | None = None,
            frequency_penalty: float | None = None,
            **kwargs
    ) -> ChatCompletionRes:
        """普通非流式响应"""
        messages = self._convert_messages(messages)
        logger.info("OpenAI chat_completion start...")
        start_at = time.time()
        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or NOT_GIVEN,
                max_tokens=max_tokens or NOT_GIVEN,
                top_p=top_p or NOT_GIVEN,
                n=n or NOT_GIVEN,
                frequency_penalty=frequency_penalty or NOT_GIVEN,
                stream=False,
                **kwargs
            )
        except Exception as e:
            logger.error(f"OpenAI chat_completion failed, err={e}")
            end_at = time.time()
            return ChatCompletionRes(
                start_at=int(start_at * 1000),
                end_at=int(end_at * 1000),
                error=str(e)
            )
        else:
            end_at = time.time()
            logger.info(f"OpenAI chat_completion cost: {(end_at - start_at):.2f}s")
            return ChatCompletionRes(
                chat_completion=response,
                start_at=int(start_at * 1000),
                end_at=int(end_at * 1000)
            )

    async def chat_completion_stream(
            self,
            messages: list[dict[str, Any]],
            *,
            max_tokens: int = None,
            temperature: float = None,
            top_p: float = None,
            n: int = 1,
            **kwargs
    ) -> AsyncGenerator[str | None, None]:
        """流式响应，返回逐块内容"""
        messages = self._convert_messages(messages)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature or NOT_GIVEN,
            max_tokens=max_tokens or NOT_GIVEN,
            top_p=top_p or NOT_GIVEN,
            n=n or NOT_GIVEN,
            stream=True,
            **kwargs
        )

        for chunk in response:
            delta = chunk.choices[0].delta
            if hasattr(delta, "content") and delta.content:
                yield delta.content
