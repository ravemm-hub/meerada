"""Shared field types for boundary schemas."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field

# Money is Decimal, never float (CLAUDE.md). Serialized as a JSON string to stay exact.
Money = Annotated[Decimal, Field(ge=0)]
