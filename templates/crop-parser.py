"""Parser for crop lists in HSE data"""

# Typical result:
# [{'crop': 'wheat', 'qualifiers': ['winter', 'undersown with grass', 'seed']}]


from lark import Lark, Transformer
from lark.visitors import v_args
from lib.template_state import TemplateState
from lib.template_support import register_fn

crop_parser = Lark(r"""
    crop_list: crop | [crop ","]+ crop
    crop: cropname ["(" qualifier_list ")"]
    cropname: NAME+
    qualifier_list: qualifier | [qualifier ","]+ qualifier
    qualifier: NAME+
    NAME: ("-"|LETTER|"_"|"/"|":"|"'")+

    %import common.WORD
    %import common.LETTER                   
    %import common.WS
    %ignore WS
    """, start='crop_list')

class CropTransformer(Transformer):
    def crop_list(self, children):
        return children
    @v_args(inline=True)    
    def crop(self, cropname, qualifiers=None):
        if qualifiers:
            return {"crop": cropname, "qualifiers": qualifiers}
        else:
            return {"crop": cropname}
    def cropname(self, children):
        return ' '.join( children )
    def qualifier_list(self, children):
        return children
    def qualifier(self, children):
        return ' '.join( children )

def parse(text: str, state: TemplateState = None):
    parse = crop_parser.parse(text)
    return CropTransformer().transform(parse)

def checks():
    print(parse("barley"))
    print(parse("barley, wheat (winter)"))
    print(parse("oilseed rape (winter), ornamental plant production"))
    print(parse("wheat (winter, undersown with grass, seed)"))

# checks()
register_fn("crop_parse", parse)
