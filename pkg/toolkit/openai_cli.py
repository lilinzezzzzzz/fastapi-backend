import time
from typing import Any, AsyncGenerator, NamedTuple

import openai
# 导入所有可能用到的异常类型，以便更精确地捕获
from openai import (
    APIError, NOT_GIVEN
)
from openai.types.chat import (
    ChatCompletion, ChatCompletionAssistantMessageParam, ChatCompletionDeveloperMessageParam,
    ChatCompletionFunctionMessageParam, ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam, ChatCompletionUserMessageParam
)
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from pkg.toolkit.logger import logger  # 假设这个日志模块是可用的


class ChatCompletionRes(NamedTuple):
    """聊天补全结果的封装，包含时间戳和结果/错误信息"""
    start_at: int  # 毫秒时间戳
    end_at: int  # 毫秒时间戳
    chat_completion: ChatCompletion | None = None
    error: str | dict | None = None


class OpenAIClient:
    """封装 OpenAI 客户端，提供非流式和流式聊天补全功能"""

    def __init__(self, base_url: str, model: str, timeout: int = 180, api_key: str = "password"):
        # 优化：API key 最好从环境变量或配置中获取，而不是硬编码默认值
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
        """统一将 messages 转换为符合 OpenAI SDK 的格式，并进行基本校验"""
        if not messages:
            return []

        converted: list[ChatCompletionMessageParam] = []
        for i, msg in enumerate(messages):
            role = msg.get("role")
            content = msg.get("content")

            if not role:
                # 优化：使用更具体的异常类型
                raise ValueError(f"Invalid message[{i}] missing role: {msg}")

            # 优化：只传递非 None 的可选参数，使消息体更简洁
            if role == "user":
                converted.append(ChatCompletionUserMessageParam(role="user", content=content))
            elif role == "system":
                converted.append(ChatCompletionSystemMessageParam(role="system", content=content))
            elif role == "assistant":
                params = {"role": "assistant", "content": content}
                if msg.get("tool_calls") is not None:
                    params["tool_calls"] = msg["tool_calls"]
                if msg.get("function_call") is not None:
                    params["function_call"] = msg["function_call"]
                # 忽略不太常用的 refusal/audio 等，除非确定需要支持
                converted.append(ChatCompletionAssistantMessageParam(**params))
            elif role == "developer":
                params = {"role": "developer", "content": content}
                if msg.get("name") is not None:
                    params["name"] = msg["name"]
                converted.append(ChatCompletionDeveloperMessageParam(**params))
            elif role == "tool":
                if not msg.get("tool_call_id"):
                    raise ValueError(f"Tool message[{i}] missing required 'tool_call_id'")
                converted.append(ChatCompletionToolMessageParam(
                    role="tool",
                    content=content,
                    tool_call_id=msg["tool_call_id"],
                ))
            elif role == "function":
                if not msg.get("name"):
                    raise ValueError(f"Function message[{i}] missing required 'name'")
                converted.append(ChatCompletionFunctionMessageParam(
                    role="function",
                    content=content,
                    name=msg["name"],
                ))
            else:
                raise ValueError(f"Invalid role '{role}' at message[{i}]")

        return converted

    # 优化：将所有 ChatCompletion 创建参数集中到一个私有方法，便于复用和管理默认值
    def _get_completion_params(
        self,
        messages: list[dict[str, Any]],
        stream: bool,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        n: int | None = None,
        frequency_penalty: float | None = None,
        **kwargs
    ) -> dict[str, Any]:
        """构建 OpenAI chat.completions.create 的参数字典"""
        return {
            "model": self.model,
            "messages": self._convert_messages(messages),
            # 使用 `if param is not None else NOT_GIVEN` 模式，确保 None 不会作为参数值传递，
            # 而是让 API 使用其默认值
            "temperature": temperature if temperature is not None else NOT_GIVEN,
            "max_tokens": max_tokens if max_tokens is not None else NOT_GIVEN,
            "top_p": top_p if top_p is not None else NOT_GIVEN,
            # n: 流式通常只能是 1，非流式可以 > 1，此处保持灵活
            "n": n if n is not None else NOT_GIVEN,
            "frequency_penalty": frequency_penalty if frequency_penalty is not None else NOT_GIVEN,
            "stream": stream,
            **kwargs
        }

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
        logger.info("OpenAI chat_completion start...")
        start_at = time.time()

        try:
            params = self._get_completion_params(
                messages, False, max_tokens, temperature, top_p, n, frequency_penalty, **kwargs
            )
            response: ChatCompletion = await self.client.chat.completions.create(**params)

        # 优化：捕获更具体的 OpenAI 异常，而不仅仅是通用的 Exception
        except (APIError, TimeoutError, ValueError) as e:
            # ValueError 来自 _convert_messages
            err_type = type(e).__name__
            logger.error(f"OpenAI chat_completion failed ({err_type}), err={e}")
            end_at = time.time()
            return ChatCompletionRes(
                start_at=int(start_at * 1000),
                end_at=int(end_at * 1000),
                error=str(e)
            )
        else:
            end_at = time.time()
            logger.info(f"OpenAI chat_completion cost: {(end_at - start_at):.2f}s, id: {response.id}")
            return ChatCompletionRes(
                chat_completion=response,
                start_at=int(start_at * 1000),
                end_at=int(end_at * 1000)
            )

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        # 优化：使用 Optional[type]
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        n: int | None = None,  # n=1 可以在内部实现，但外部接口保持一致
        frequency_penalty: float | None = None,
        **kwargs
    ) -> AsyncGenerator[str | None, None]:
        """流式响应，返回逐块内容，带有错误处理"""
        start_at = time.time()
        logger.info("OpenAI chat_completion_stream start...")

        try:
            params = self._get_completion_params(
                messages, True, max_tokens, temperature, top_p, n, frequency_penalty, **kwargs
            )

            # response 的类型是 AsyncStream[ChatCompletionChunk]
            response = await self.client.chat.completions.create(**params)

            # 优化：迭代流式响应，添加健壮性检查
            async for chunk in response:
                if not isinstance(chunk, ChatCompletionChunk):
                    continue  # 确保是正确的 chunk 类型

                delta = chunk.choices[0].delta
                # 检查 content 属性是否存在且不为空
                if hasattr(delta, "content") and delta.content is not None:
                    yield delta.content
                # 优化：处理可能的 tool_calls 或 function_call (可选，但推荐)
                # elif hasattr(delta, "tool_calls") and delta.tool_calls:
                #     ...
                # elif hasattr(delta, "function_call") and delta.function_call:
                #     ...

        # 优化：添加 try...except 块捕获流式请求中的错误
        except (APIError, TimeoutError, ValueError) as e:
            err_type = type(e).__name__
            logger.error(f"OpenAI chat_completion_stream failed ({err_type}), err={e}")
            # 在流式生成器中，通常通过重新抛出异常或 yield 一个错误标记来通知调用者。
            # 这里选择记录错误并允许生成器停止。如果需要向调用者返回错误，需要修改生成器的返回类型。
            # 由于原函数返回的是 `AsyncGenerator[str | None, None]`，我们可以 yield 一个 None 来表示结束，
            # 但最好的做法是让异常冒泡或在外部处理。
            # 为了兼容性，这里只是记录并退出循环，让生成器自然结束。
            pass
        finally:
            end_at = time.time()
            logger.info(f"OpenAI chat_completion_stream end, cost: {(end_at - start_at):.2f}s")
