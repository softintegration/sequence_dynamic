Dynamic sequence settings
-----------------------------
This module allow the administrator to configure sequence so that the prefix can be assigned dynamically basing on value of fields in model related to sequence.


> **_Usage requirements:_**  
* To use the dynamic sequence,the sequence used by the object must be __Sequence template__.
* Any object that want to use dynamic sequence must edit its call to __Sequence template__ by adding the dictionary of dynamic fields like this : ___with_context(dynamic_prefix_fields={'code':vals['code'],...})___.