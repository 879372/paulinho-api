"""Compatibilidade temporária. Views HTTP vivem em core.api.<domínio>.views."""
from core.api.common.throttles import LoginThrottle

__all__ = ['LoginThrottle']
