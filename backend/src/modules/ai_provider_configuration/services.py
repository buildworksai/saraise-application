"""
AiProviderConfiguration Services.

High-level service layer for AiProviderConfiguration business logic.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx
from django.db import transaction

from .models import AIProvider, AIProviderCredential

logger = logging.getLogger(__name__)


class AIProviderService(ABC):
    """Abstract base class for AI provider services."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        """Initialize provider service.

        Args:
            api_key: API key for the provider.
            base_url: Optional base URL (uses default if None).
        """
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Complete a prompt using the AI provider.

        Args:
            prompt: Input prompt.
            model: Model identifier.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.

        Returns:
            Generated text.

        Raises:
            Exception: If API call fails.
        """
        pass


class OpenAIProvider(AIProviderService):
    """OpenAI provider implementation."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        """Initialize OpenAI provider."""
        super().__init__(api_key, base_url)
        self.base_url = base_url or "https://api.openai.com/v1"

    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Complete prompt using OpenAI API."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text}")
            raise ValueError(f"OpenAI API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"OpenAI API request failed: {e}")
            raise ValueError(f"Failed to complete OpenAI request: {e}")


class AnthropicProvider(AIProviderService):
    """Anthropic provider implementation."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        """Initialize Anthropic provider."""
        super().__init__(api_key, base_url)
        self.base_url = base_url or "https://api.anthropic.com/v1"

    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Complete prompt using Anthropic API."""
        url = f"{self.base_url}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Anthropic API error: {e.response.status_code} - {e.response.text}")
            raise ValueError(f"Anthropic API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Anthropic API request failed: {e}")
            raise ValueError(f"Failed to complete Anthropic request: {e}")


class GoogleGeminiProvider(AIProviderService):
    """Google Gemini provider implementation."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        """Initialize Google Gemini provider."""
        super().__init__(api_key, base_url)
        self.base_url = base_url or "https://generativelanguage.googleapis.com/v1"

    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Complete prompt using Google Gemini API."""
        url = f"{self.base_url}/models/{model}:generateContent"
        params = {"key": self.api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }

        try:
            response = httpx.post(url, params=params, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Google Gemini API error: {e.response.status_code} - {e.response.text}")
            raise ValueError(f"Google Gemini API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Google Gemini API request failed: {e}")
            raise ValueError(f"Failed to complete Google Gemini request: {e}")


class GroqProvider(AIProviderService):
    """Groq provider implementation (OpenAI-compatible API)."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        """Initialize Groq provider."""
        super().__init__(api_key, base_url)
        self.base_url = base_url or "https://api.groq.com/openai/v1"

    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Complete prompt using Groq API (OpenAI-compatible)."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Groq API error: {e.response.status_code} - {e.response.text}")
            raise ValueError(f"Groq API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Groq API request failed: {e}")
            raise ValueError(f"Failed to complete Groq request: {e}")


class HuggingFaceProvider(AIProviderService):
    """HuggingFace Inference API provider implementation."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        """Initialize HuggingFace provider."""
        super().__init__(api_key, base_url)
        self.base_url = base_url or "https://api-inference.huggingface.co"

    def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Complete prompt using HuggingFace Inference API."""
        url = f"{self.base_url}/models/{model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
            },
        }

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()

            # HuggingFace returns different formats depending on model type
            if isinstance(data, list) and len(data) > 0:
                # Text generation models return list with generated_text
                return data[0].get("generated_text", "")
            elif isinstance(data, dict) and "generated_text" in data:
                return data["generated_text"]
            else:
                # Fallback: try to extract text from response
                return str(data)
        except httpx.HTTPStatusError as e:
            logger.error(f"HuggingFace API error: {e.response.status_code} - {e.response.text}")
            raise ValueError(f"HuggingFace API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"HuggingFace API request failed: {e}")
            raise ValueError(f"Failed to complete HuggingFace request: {e}")


class AIProviderFactory:
    """Factory for creating AI provider service instances."""

    @staticmethod
    def get_provider(provider_type: str, tenant_id: str) -> AIProviderService:
        """Get provider service instance for tenant.

        Args:
            provider_type: Provider type (openai, anthropic, etc.).
            tenant_id: Tenant ID.

        Returns:
            AIProviderService instance.

        Raises:
            ValueError: If provider not found or credentials missing.
        """
        provider = AIProvider.objects.filter(
            provider_type=provider_type,
            is_active=True,
        ).first()

        if not provider:
            raise ValueError(f"Provider {provider_type} not found or inactive")

        credential = AIProviderCredential.objects.filter(
            tenant_id=tenant_id,
            provider=provider,
        ).first()

        if not credential:
            raise ValueError(f"Credentials not found for provider {provider_type} and tenant {tenant_id}")

        # Decrypt API key
        from src.core.encryption import EncryptionService

        api_key = EncryptionService.decrypt(credential.api_key_encrypted)

        if provider_type == "openai":
            return OpenAIProvider(api_key, provider.base_url)
        elif provider_type == "anthropic":
            return AnthropicProvider(api_key, provider.base_url)
        elif provider_type == "google":
            return GoogleGeminiProvider(api_key, provider.base_url)
        elif provider_type == "groq":
            return GroqProvider(api_key, provider.base_url)
        elif provider_type == "huggingface":
            return HuggingFaceProvider(api_key, provider.base_url)
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")
