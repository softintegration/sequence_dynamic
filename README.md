Dynamic sequence settings
-----------------------------
This module allow the administrator to configure sequence so that the prefix can be assigned dynamically basing on value of fields in model related to sequence.


> **_Usage requirements:_**  
* To use the dynamic sequence,the sequence used by the object must be __Sequence template__.
* Any object that want to use dynamic sequence must edit its call to __Sequence template__ by adding the dictionary of dynamic fields like this : ___with_context(dynamic_prefix_fields={'code':vals['code'],...})___ or error message __No dynamic prefix fields has been found!__ will be displayed.

>Note that the second requirement can't be done dynamically because of the variable nature of how objects call the sequence service