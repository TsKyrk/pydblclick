Initial bug:
a python script using the __file__ variable to get its filesystem location would fail in pydblclick.

Explanation:
globals() initialized in the pydblclick context is not the same as globals() in a normal execution context.

In the normal context:
{'__annotations__': {},
 '__builtins__': <module 'builtins' (built-in)>,
 '__cached__': None,
 '__doc__': None,
 '__file__': 'D:\\05_Prog\\01_MesRepos\\pydblclick\\unit_tests\\E004_Reading__file__(normal).py',
 '__loader__': <_frozen_importlib_external.SourceFileLoader object at 0x000001CC5DFF6090>,
 '__name__': '__main__',
 '__package__': None,
 '__spec__': None,
 'pp': <module 'pprint' from 'D:\\02_Programs\\Python\\Python3.11.3\\Lib\\pprint.py'>}
 
In the pydblclick context:
{'User32': <class '__main__.User32'>,
 '__annotations__': {},
 '__builtins__': <module 'builtins' (built-in)>,
 '__cached__': 'D:\\05_Prog\\01_MesRepos\\pydblclick\\pydblclick\\__pycache__\\__main__.cpython-311.pyc',     =====> cached compiled version of the code
 '__doc__': None,
 '__file__': 'D:\\05_Prog\\01_MesRepos\\pydblclick\\pydblclick\\__main__.py',                                 =====> MUST BE CHANGED !!!!
 '__loader__': <_frozen_importlib_external.SourceFileLoader object at 0x0000022635F8A910>,
 '__name__': '__main__',
 '__package__': 'pydblclick',                                                                                =====> SHOULD BE CHANGED !!!
 '__spec__': ModuleSpec(name='pydblclick.__main__', loader=<_frozen_importlib_external.SourceFileLoader object at 0x0000022635F8A910>, origin='D:\\05_Prog\\01_MesRepos\\pydblclick\\pydblclick\\__main__.py'),                                     =====> SHOULD BE CHANGED !!!
 'code': <module 'code' from 'D:\\02_Programs\\Python\\Python3.11.3\\Lib\\code.py'>,                        =====> parasitic import
 'copy': <module 'copy' from 'D:\\02_Programs\\Python\\Python3.11.3\\Lib\\copy.py'>,                        =====> parasitic import
 'display_pause_prompt_and_menu': <function display_pause_prompt_and_menu at 0x0000022636529580>,           =====> parasitic symbol
 'main': <function main at 0x0000022636529620>,                                                             =====> parasitic symbol
 'os': <module 'os' (frozen)>,                                                                              =====> parasitic import
 'pp': <module 'pprint' from 'D:\\02_Programs\\Python\\Python3.11.3\\Lib\\pprint.py'>,                      =====> parasitic import
 'pydblclick_must_pause_in_console': True,                                                                   =====> ok
 'showtraceback': <function showtraceback at 0x000002263622F560>,                                           =====> parasitic import
 'sys': <module 'sys' (built-in)>,                                                                          =====> parasitic import
 'traceback': <module 'traceback' from 'D:\\02_Programs\\Python\\Python3.11.3\\Lib\\traceback.py'>}         =====> parasitic import
Press <Enter> to Quit. (<c> for cmd console. <i> for interactive python. <r> to restart.)

Solution:
Now exec(code) is run using cherry-picked globals() and locals()
especially __local__ is initialized to the proper path