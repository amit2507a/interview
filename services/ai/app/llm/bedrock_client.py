"""
AWS Bedrock LLM Client
Wraps boto3 Bedrock Runtime with retry logic and structured logging.
"""
import json
import boto3
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog

from app.config import settings

logger = structlog.get_logger()


class BedrockClient:
    """
    Thin wrapper around AWS Bedrock for Claude calls.
    All scoring calls MUST use temperature=0 for reproducibility.
    """

    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.BEDROCK_REGION,
        )
        self.model_id = settings.BEDROCK_MODEL_ID

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def generate(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        system_prompt: str | None = None,
    ) -> str:
        """
        Call Bedrock Claude with retry on transient failures.
        Returns raw text response.
        """
        messages = [{"role": "user", "content": prompt}]
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system_prompt:
            body["system"] = system_prompt

        logger.debug("LLM call", model=self.model_id, temperature=temperature)

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
