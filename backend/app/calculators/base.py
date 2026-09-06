"""Calculator engine.

A calculator declares its inputs (with the entity types that can feed each one
from extracted document data) and produces a result that always carries the
formula, the input values with their sources, intermediate steps, assumptions
and a classification that keeps calculated values distinct from
manufacturer-documented ones.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable


@dataclass
class SourceRef:
    document_id: str | None = None
    document_name: str | None = None
    page: int | None = None
    section: str | None = None
    entity_id: str | None = None
    snippet: str | None = None
    confidence: float | None = None


@dataclass
class InputSpec:
    key: str
    label: str
    unit: str | None = None
    kind: str = "number"  # number | select | text
    required: bool = True
    default: Any = None
    options: list[dict] | None = None
    help: str | None = None
    entity_types: list[str] = field(default_factory=list)  # document entity types that can populate this input
    qualifiers: list[str] = field(default_factory=list)  # preferred entity qualifiers


@dataclass
class CalculatorSpec:
    id: str
    name: str
    category: str
    description: str
    formula: str
    inputs: list[InputSpec]
    outputs: list[dict]
    notes: list[str] = field(default_factory=list)


@dataclass
class InputValue:
    value: Any
    unit: str | None = None
    source: SourceRef | None = None
    origin: str = "user"  # user | document | default


@dataclass
class ResultValue:
    key: str
    label: str
    value: Any
    unit: str | None = None
    classification: str = "calculated_estimate"  # manufacturer_required | calculated_estimate | recommended_pending_verification | documented_value
    note: str | None = None


@dataclass
class CalcResult:
    calculator_id: str
    calculator_name: str
    formula: str
    inputs: dict[str, InputValue]
    steps: list[str]
    results: list[ResultValue]
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    classification: str = "calculated_estimate"
    disclaimer: str = (
        "This is an engineering estimate computed from the inputs shown. It is not a manufacturer "
        "specification unless the input source says so. Verify against the manufacturer's documentation and "
        "applicable standards (e.g. ABYC E-11, ISO 13297) before installation."
    )

    def to_dict(self) -> dict:
        return asdict(self)


class Calculator:
    spec: CalculatorSpec

    def __init__(self, spec: CalculatorSpec, fn: Callable[[dict[str, InputValue]], CalcResult]):
        self.spec = spec
        self._fn = fn

    def run(self, raw_inputs: dict[str, Any]) -> CalcResult:
        inputs = coerce_inputs(self.spec, raw_inputs)
        result = self._fn(inputs)
        result.sources = [iv.source for iv in inputs.values() if iv.source]
        return result


class CalculationError(ValueError):
    pass


def coerce_inputs(spec: CalculatorSpec, raw: dict[str, Any]) -> dict[str, InputValue]:
    out: dict[str, InputValue] = {}
    for inp in spec.inputs:
        item = raw.get(inp.key)
        if isinstance(item, dict) and "value" in item:
            value = item.get("value")
            unit = item.get("unit") or inp.unit
            src = item.get("source")
            source = SourceRef(**{k: v for k, v in src.items() if k in SourceRef.__dataclass_fields__}) if isinstance(src, dict) else None
            origin = "document" if source else "user"
        else:
            value, unit, source, origin = item, inp.unit, None, "user"
        if value is None or value == "":
            if inp.default is not None:
                value, origin = inp.default, "default"
            elif inp.required:
                raise CalculationError(f"Missing required input: {inp.label}")
            else:
                out[inp.key] = InputValue(value=None, unit=unit, source=None, origin="user")
                continue
        if inp.kind == "number":
            try:
                value = float(str(value).replace(",", ""))
            except ValueError as exc:
                raise CalculationError(f"{inp.label} must be a number (got {value!r})") from exc
        out[inp.key] = InputValue(value=value, unit=unit, source=source, origin=origin)
    return out


def num(inputs: dict[str, InputValue], key: str) -> float | None:
    iv = inputs.get(key)
    return None if iv is None or iv.value is None else float(iv.value)


def fmt(v: float, digits: int = 2) -> str:
    if v is None:
        return "—"
    if abs(v) >= 100:
        return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.1f}"
    return f"{v:.{digits}f}".rstrip("0").rstrip(".")
