"""Parser for ingredients lists in HSE data"""

# Typical result
# [{'concentration': Decimal('0.015'), 'unit': 'g/l', 'substance': 'lambda-cyhalothrin'}]


from lark import Lark, Transformer
from lark.visitors import v_args
from decimal import Decimal
from rdf_mapper.lib.template_state import TemplateState
from rdf_mapper.lib.template_support import register_fn

substance_parser = Lark(r"""
    ingredient_list: ingredient
        | ingredient "and" ingredient
        | [ingredient ","]+ ingredient "and" ingredient
    ingredient: concentration substance
    concentration: concentration_amount "%" percentconc
        | concentration_amount unit "/" unit
    concentration_amount: NUMBER [["x"] "10^" INT]
    unit: "g"  -> unit_g
        | "kg" -> unit_kg
        | "l" -> unit_l
        | "ml" -> unit_ml
        | "ul" -> unit_ul
        | "CFU" -> unit_cfu
        | "GV" -> unit_gv
        | "vgc" -> unit_vgc
    percentconc: "w/w"  -> ww
        | "w/v" -> wv
        | "v/v"  -> vv

    substance: COMPLEX_NAME+

    COMPLEX_NAME: [("-"|LETTER|DIGIT|"_"|":"|"("|")"|","|"/"|".")+] (LETTER|DIGIT|"."|"-"|":"|")")+
    NAME: LETTER ("-"|LETTER)*

    %import common.WORD
    %import common.LETTER
    %import common.NUMBER
    %import common.DIGIT
    %import common.INT
    %import common.WS
    %ignore WS

    """, start='ingredient_list')

class SubstanceTransformer(Transformer):
    def concentration_amount(self, children):
        amount, expt = children
        return Decimal(amount + 'e' + expt) if expt else Decimal(amount)
    @v_args(inline=True)
    def concentration(self, amount, numerator_or_by, denominator=None):
        if denominator:
            return {"amount" : amount, "numerator": numerator_or_by.data.replace('unit_',''), 
                    "denominator": denominator.data.replace('unit_','')}
        else:
            return {"amount" : amount, "percent": numerator_or_by.data.replace('unit_','')}
    def ingredient(self, children):
        concentration, substance = children
        unit = None
        if "percent" in concentration:
            unit = "%" + concentration['percent']
        else:
            unit = concentration['numerator'] + "/" + concentration['denominator']
        return {"concentration": concentration['amount'], "unit": unit, "substance": substance}
    def ingredient_list(self, children):
        return children
    def substance(self, tree):
        return ' '.join( tree )

def parse(text: str, state: TemplateState = None):
    try:
        parse = substance_parser.parse(text)
        return SubstanceTransformer().transform(parse)
    except Exception as err:
        raise ValueError(f"Ingredient parse failed on {text} due to {err}")

def checks():
    print(parse("100.000 g / l 1-naphthylacetic acid"))
    print(parse("1.000 10^12 CFU/kg coniothyrium minitans strain CON/M/91-08 (DSM 9660)"))
    print(parse("100.000 % w/w Spearmint Oil"))
    print(parse("0.015 g / l lambda-cyhalothrin"))
    print(parse("0.729 g / l 2,4-D"))
    print(parse("0.576 g / l diflufenican and 3.600 g / l glyphosate"))
    print(parse("0.729 g / l 2,4-D, 0.235 g / l dicamba, 0.745 g / l MCPA and 0.464 g / l mecoprop-P"))

# checks()
register_fn("ingredient_parse", parse)
