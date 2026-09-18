"""LLM Provider abstraction layer.

Thin wrapper over LLM providers that keeps THIRA engine code provider-agnostic.
Uses litellm under the hood for multi-provider routing.
"""
