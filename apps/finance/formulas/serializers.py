from __future__ import annotations

from rest_framework import serializers

from apps.finance.formulas.constants import (
    MAX_CONSTRUCTOR_BLOCKS,
    MAX_FORMULA_CODE_LENGTH,
)


class FormulaIdeCanvasBlockSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=80)
    kind = serializers.ChoiceField(choices=["function", "variable", "operator", "condition"])
    label = serializers.CharField(max_length=200)


class FormulaIdeStateResponseSerializer(serializers.Serializer):
    formula_id = serializers.CharField()
    code = serializers.CharField()
    constructor_blocks = FormulaIdeCanvasBlockSerializer(many=True)
    updated_at = serializers.DateTimeField(allow_null=True, required=False)
    is_saved = serializers.BooleanField()


class FormulaIdeStateSaveResponseSerializer(serializers.Serializer):
    formula_id = serializers.CharField()
    updated_at = serializers.DateTimeField()
    is_saved = serializers.BooleanField()


class FormulaIdeStateUpdateSerializer(serializers.Serializer):
    code = serializers.CharField(
        allow_blank=True,
        trim_whitespace=False,
        max_length=MAX_FORMULA_CODE_LENGTH,
    )
    constructor_blocks = serializers.ListField(
        child=FormulaIdeCanvasBlockSerializer(),
        required=False,
        allow_empty=True,
        max_length=MAX_CONSTRUCTOR_BLOCKS,
    )


class FormulaIdePaletteGroupSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    chip_class = serializers.ChoiceField(choices=["period", "function", "operator", "constant"])
    items = serializers.ListField(child=serializers.CharField())


class FormulaIdeConstructorVariableSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    icon = serializers.CharField()


class FormulaIdeConstructorOperatorSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()


class FormulaIdeAutocompleteItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()


class FormulaIdeMetaResponseSerializer(serializers.Serializer):
    variable_groups = FormulaIdePaletteGroupSerializer(many=True)
    constructor_variables = FormulaIdeConstructorVariableSerializer(many=True)
    constructor_operators = FormulaIdeConstructorOperatorSerializer(many=True)
    autocomplete_items = FormulaIdeAutocompleteItemSerializer(many=True)


class FormulaIdeValidationRequestSerializer(serializers.Serializer):
    code = serializers.CharField(
        allow_blank=True,
        trim_whitespace=False,
        help_text="DSL-код формулы для проверки.",
    )


class FormulaIdeDiagnosticSerializer(serializers.Serializer):
    id = serializers.CharField()
    line = serializers.IntegerField(min_value=1)
    message = serializers.CharField()
    severity = serializers.ChoiceField(choices=["error", "warning"], default="error")


class FormulaIdeValidationResponseSerializer(serializers.Serializer):
    is_valid = serializers.BooleanField()
    errors = FormulaIdeDiagnosticSerializer(many=True)


class FormulaIdePreviewRequestSerializer(serializers.Serializer):
    code = serializers.CharField(
        allow_blank=True,
        trim_whitespace=False,
        help_text="DSL-код формулы для предпросмотра.",
    )
    constructor_blocks = serializers.ListField(
        child=FormulaIdeCanvasBlockSerializer(),
        required=False,
        allow_empty=True,
        max_length=MAX_CONSTRUCTOR_BLOCKS,
        help_text="Блоки визуального конструктора. На текущем этапе используются для хранения и совместимости с FE.",
    )

class FormulaIdePreviewRowSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    value = serializers.CharField()
    highlight = serializers.BooleanField(default=False)

class FormulaIdePreviewChartPointSerializer(serializers.Serializer):
    month = serializers.CharField()
    value = serializers.FloatField()

class FormulaIdePreviewResponseSerializer(serializers.Serializer):
    rows = FormulaIdePreviewRowSerializer(many=True)
    chart_points = FormulaIdePreviewChartPointSerializer(many=True)
