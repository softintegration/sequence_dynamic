# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError
import datetime

DYNAMIC_PREFIX_DELIMITER = '%'
DYNAMIC_PREFIX_START_VAR = '('
DYNAMIC_PREFIX_END_VAR = ')'
DYNAMIC_PREFIX_STATIC_VALUE_DELIMITER = '**'
DYNAMIC_PREFIX_PADDING_START = '['
DYNAMIC_PREFIX_PADDING_END = ']'

TYPE_DYNAMIC_SUFF_CODE = 'dynamic_suffix_code'
TYPE_DYNAMIC_PREF_CODE = 'dynamic_prefix_code'
TYPE_CODE_GENERATOR = 'sequence_generator_code'


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    sequence = fields.Integer(string='Sequence', help="Order the Sequence templates")
    sequence_type = fields.Selection([('sequence', 'Sequence'),
                                      ('sequence_template', 'Sequence template')], required=True, default='sequence')
    related_model = fields.Many2one('ir.model', string='Model using this sequence',
                                    help="This will help to control the dynamic prefix field before its usage "
                                         "(as no hard relation existing between object and sequence,with this data the system will be able to compare "
                                         "the fields put in the dynamic part with the controls existing on this Model)")
    dynamic_prefix_code = fields.Text(string='Dynamic prefix codification',
                                      help='Please take in account all this constraints specified under <Legend for dynamic prefix>')
    generate_new_sequence = fields.Boolean(string='Generate sequence by format', default=True,
                                           help="Select this if you want to generate new sequence for each new format detected")
    sequence_generator_code = fields.Text(string='Sequence generator code',
                                          help='This is used to generate sequence relying on the variation of the value of this code'
                                               ",the same codification syntax used by the Dynamic prefix codification is applicable here")
    default_sequence_id = fields.Many2one('ir.sequence', string='Default sequence',
                                          help="Use a default sequence if you want to generate a reference even in the case where one or more values among those used in the sequence generator code are null")
    dynamic_suffix_code = fields.Text(string='Dynamic suffix codification',
                                      help='Please take in account all this constraints specified under <Legend for dynamic prefix>')
    generator_code = fields.Char('Generator code', readonly=False,
                                 help='This code is unique by sequence,and is used to generate new sequence or return sequence it match')
    parent_id = fields.Many2one('ir.sequence', string='Parent sequence',
                                help='The sequence model that create this sequence')
    child_ids = fields.Many2many('ir.sequence', compute='_compute_child_ids')
    child_count = fields.Integer(compute='_compute_child_count')

    _sql_constraints = [
        ('generator_code_uniq', 'unique (generator_code,company_id)', "Generator_code name already exists !")]

    # FIXME: this method must be removed from here
    @api.model
    def _translate_dynamic_values(self, src):
        domain = [('src', '=', src), ('lang', '=', self.env.context.get('lang'))]
        return self.env['ir.translation'].search(domain, limit=1).value or src

    @api.depends('child_ids')
    def _compute_child_count(self):
        self.child_count = len(self.child_ids)

    def _compute_child_ids(self):
        domain = [('parent_id', '=', self.id)]
        self.child_ids = self.search(domain).ids

    def action_view_child_sequences(self):
        return self._get_action_view_sequences(self.child_ids)

    def _get_action_view_sequences(self, sequences):
        action = self.env["ir.actions.actions"]._for_xml_id("base.ir_sequence_form")

        if len(sequences) > 1:
            action['domain'] = [('id', 'in', sequences.ids)]
        elif sequences:
            form_view = [(self.env.ref('base.sequence_view').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state, view) for state, view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = sequences.id
        # Prepare the context.
        action['context'] = dict(self._context, default_parent_id=self.id)
        return action

    @api.constrains('sequence_type', 'related_model', 'dynamic_prefix_code', 'sequence_generator_code')
    def _check_dynamic_prefix_code(self):
        if self.sequence_type == 'sequence_template' and self.related_model:
            if self.dynamic_prefix_code:
                self._check_dynamic_prefix_code_syntax(self.dynamic_prefix_code, self.related_model.model)
            elif self.sequence_generator_code:
                self._check_dynamic_prefix_code_syntax(self.sequence_generator_code, self.related_model.model)
            else:
                raise ValidationError(
                    _("In sequence template,at least Dynamic prefix or Sequence generator code must be used!"))

    @api.model
    def _check_dynamic_prefix_code_syntax(self, dynamic_prefix_code, model_name):
        valid_syntax = dynamic_prefix_code.count(DYNAMIC_PREFIX_DELIMITER) == 1 and dynamic_prefix_code.count(
            DYNAMIC_PREFIX_START_VAR) == 1 \
                       and dynamic_prefix_code.count(DYNAMIC_PREFIX_END_VAR) == 1
        if not valid_syntax:
            raise ValidationError(
                _('Invalid syntax for the dynamic prefix/Sequence generator code,please check the rules in Legend for dynamic prefix/Sequence generator code'))
        fields = self._parse_fields_for_check(dynamic_prefix_code)
        for field in fields:
            try:
                getattr(self.env[model_name], field)
            except AttributeError as e:
                raise ValidationError(_('No field %s detected in model %s') % (
                    field, self._translate_dynamic_values(self.env[model_name]._description)))

    @api.model
    def _parse_fields_for_check(self, dynamic_prefix_code):
        fields_list = self._parse_fields(dynamic_prefix_code, remove_static_fields=True)
        # for the check purpose we need only the first field not the nested one
        return [field.split(".")[0] for field in fields_list]

    @api.model
    def _parse_fields(self, dynamic_prefix_code, remove_static_fields=False):
        field_list = self._parse_dynamic_prefix_variable(dynamic_prefix_code)
        if not remove_static_fields:
            return field_list
        field_list = [field for field in field_list if field not in self._parse_static_fields(dynamic_prefix_code)]
        return field_list

    @api.model
    def _parse_static_fields(self, dynamic_prefix_code):
        field_list = self._parse_dynamic_prefix_variable(dynamic_prefix_code)
        return [field for field in field_list if field.startswith(DYNAMIC_PREFIX_STATIC_VALUE_DELIMITER)]

    @api.model
    def _parse_static_field(self, field):
        return field.replace(DYNAMIC_PREFIX_STATIC_VALUE_DELIMITER, '')

    @api.model
    def _parse_dynamic_prefix_variable(self, dynamic_prefix_code):
        fields_str = dynamic_prefix_code.replace(DYNAMIC_PREFIX_DELIMITER, '').replace(DYNAMIC_PREFIX_START_VAR, '') \
            .replace(DYNAMIC_PREFIX_END_VAR, '')
        return fields_str.split(',')

    @api.model
    def next_by_code(self, sequence_code, sequence_date=None):
        """ Inherit this method to request the template sequence if this is the case."""
        # we have to ovoid security check layer as this method must be executed without ACLs restrictions
        self = self.sudo()
        company_id = self.env.company.id
        # Here the sequence templates are with high priority in case there are sequences and sequence templates with the same code
        # and after that the sequence templates will be ordered by the sequence field,this is because we rely on the assumption that
        # if there are sequence template ,so the admin want the sequence to be managed dynamically
        seq = self.search([('code', '=', sequence_code), ('company_id', 'in', [company_id, False])],
                          order='sequence_type DESC,sequence ASC,company_id', limit=1)
        suffix = False
        if seq.dynamic_suffix_code:
            # The suffix code is not used as unique element of sequence generation so if the value of some fields are null we have to proceed
            suffix = seq._build_code(TYPE_DYNAMIC_SUFF_CODE,fields_check_strict=False)
            if not suffix:
                raise ValidationError(
                    _("Some fields used to generate dynamic sequence prefix are not defined,can not proceed!"))
            if self.env.context.get('only_dynamic_suffix_code',False):
                return suffix
        if not seq:
            return super(IrSequence, self).next_by_code(sequence_code, sequence_date=sequence_date)
        if seq.sequence_type == 'sequence':
            return super(IrSequence, self).next_by_code(sequence_code, sequence_date=sequence_date)

        # FIXME:this can have bad impact on performance since the forced_name is very rarely used,but the check will be done allways
        if not self.env.context.get('forced_name',False):
            name = seq._next_by_sequence_template(sequence_code, sequence_date=sequence_date)
        else:
            name = self.env.context.get('forced_name')
        if suffix:
            name = '%s%s' % (name, suffix)
        return name

    def next_by_id(self, sequence_date=None):
        """ Inherit this method to request the template sequence if this is the case."""
        self.check_access_rights('read')
        if self.sequence_type == 'sequence':
            return super(IrSequence, self).next_by_id(sequence_date=sequence_date)
        name = self._next_by_sequence_template(None, sequence_date=sequence_date)
        if self.dynamic_suffix_code:
            # The suffix code is not used as unique element of sequence generation so if the value of some fields are null we have to proceed
            suffix = self._build_code(TYPE_DYNAMIC_SUFF_CODE,fields_check_strict=False)
            if not suffix:
                raise ValidationError(
                    _("Some fields used to generate dynamic sequence prefix are not defined,can not proceed!"))
            name = '%s %s' % (name, suffix)
        return name

    def _next_by_sequence_template(self, sequence_code=None, sequence_date=None):
        company_id = self.env.company.id
        domain = [('company_id', 'in', [company_id, False])]
        prefix, generator_code = False, False
        if self.dynamic_prefix_code:
            prefix = self._build_code(TYPE_DYNAMIC_PREF_CODE)
            if not prefix:
                # in the case we have default sequence to use
                if self.default_sequence_id and self.default_sequence_id.sequence_type == 'sequence':
                    return self.default_sequence_id._next(sequence_date=sequence_date)
                elif self.default_sequence_id and self.default_sequence_id.sequence_type == 'sequence_template':
                    return self.default_sequence_id._next_by_sequence_template(sequence_code,
                                                                               sequence_date=sequence_date)
                raise ValidationError(
                    _("Some fields used to generate dynamic sequence prefix are not defined,can not proceed!"))
            if not self.generate_new_sequence:
                return prefix
            domain.append(('prefix', '=', prefix))
        if self.sequence_generator_code:
            generator_code = self._build_code(TYPE_CODE_GENERATOR)
            if not generator_code:
                # in the case we have default sequence to use
                if self.default_sequence_id and self.default_sequence_id.sequence_type == 'sequence':
                    return self.default_sequence_id._next(sequence_date=sequence_date)
                elif self.default_sequence_id and self.default_sequence_id.sequence_type == 'sequence_template':
                    return self.default_sequence_id._next_by_sequence_template(sequence_code,
                                                                               sequence_date=sequence_date)
                raise ValidationError(
                    _("Some fields used in the Sequence generator code are not defined,can not proceed!"))
            domain.append(('generator_code', '=', generator_code))
        if sequence_code:
            domain.append(('code', '=', sequence_code))
        seq_ids = self.search(domain, order='company_id')
        if not seq_ids:
            seq_ids |= self._create_sequence_from_template(prefix=prefix, generator_code=generator_code)
        seq_id = seq_ids[0]
        return seq_id._next(sequence_date=sequence_date)

    def _create_sequence_from_template(self, prefix=False, generator_code=False):
        new_sequence = self.sudo().copy({'prefix': prefix,
                                  'generator_code': generator_code,
                                  'parent_id': self.id,
                                  'sequence_type': 'sequence',
                                  'number_next': 1,
                                  'related_model': False,
                                  'dynamic_prefix_code': False,
                                  })
        # we have to copy the date range if the template have that
        if self.use_date_range and self.date_range_ids:
            for date_range in self.date_range_ids:
                new_date_range = date_range.copy({
                    'sequence_id': new_sequence.id,
                    'number_next_actual': date_range.number_next_actual
                })
        return new_sequence

    def _build_code(self, code_type,fields_check_strict=True):
        """
        This method is used to generate code instance relying on the fields of the model
        :param code_type (char):used to determine the type of the code dynamic_suffix_code,dynamic_prefix_code...,the behaviour
        of the method will change depending on the behaviour of this parameter
        :param fields_check_strict (bool):if this parameter is True,this method will return False if any of the fields
        is null,otherwise it will return the found code and let the check responsability to the caller method
        """
        dynamic_prefix_fields = self.env.context.get('dynamic_prefix_fields', False)
        # the model using he sequence,here we hve to get this model in the logic order,we get the model imposed in the context
        # and if it is not specified we get the model specified in the sequence template to control the dynamic fields because
        # this settings is considered as explicit specification of the model,and if this is not specified as well,we suppose that th model
        # is the code of the sequence ,this is the last assumption that can be done
        related_model = self.env.context.get('related_model', self.related_model and self.related_model.model)
        if not related_model:
            try:
                related_model = self.env[self.code]._name
            except KeyError:
                raise UserError(_("No related model detected,can not build dynamic sequence!"))
        if not dynamic_prefix_fields:
            raise UserError(_("No dynamic prefix fields has been found!"))
        record = self.env[related_model]
        fields = self._parse_fields(getattr(self, code_type))
        prefix = ''
        for field in fields:
            if field in self._parse_static_fields(getattr(self, code_type)):
                prefix += self._parse_static_field(field)
                continue
            try:
                # we have to parse the padding from the field codification
                field, padding = self._get_field_padding(field)
                # get only the field name in the case of many2one field (not all the chain)
                field_obj = record._fields[field.split(".")[0]]
            except KeyError as ae:
                raise UserError(_('No field %s detected in model %s') % (field, record._name))
            else:
                if code_type in (TYPE_DYNAMIC_PREF_CODE,) and field_obj.type not in ('char', 'many2one'):
                    raise UserError(
                        _('field used in dynamic prefix must be char or many2one,the type of field %s is %s') % (
                            field_obj.string, field_obj.type))
                if field_obj.type == 'char':
                    val = dynamic_prefix_fields[field_obj.name]
                    if not val:
                        if fields_check_strict:
                            return False
                        else:
                            val = ''
                    prefix += val
                elif field_obj.type not in ('many2one', 'one2many', 'many2many'):
                    val = dynamic_prefix_fields[field_obj.name]
                    if not val:
                        if fields_check_strict:
                            return False
                        else:
                            val = ''
                    if not padding or val == '':
                        prefix += str(val)
                    else:
                        prefix += '%%0%sd' % padding % val
                elif field_obj.type == 'many2one':
                    val = self._parse_many2one_field(record, dynamic_prefix_fields, field)
                    if not val:
                        if fields_check_strict:
                            return False
                        else:
                            val = ''
                    prefix += val
                else:
                    raise ValidationError(_("The field %s type is not authorised!") % field_obj.description)
        return prefix

    @api.model
    def _get_field_padding(self, field):
        # if no padding in field
        if field.find(DYNAMIC_PREFIX_PADDING_START) == -1 or field.find(DYNAMIC_PREFIX_PADDING_END) == -1:
            return field, 0
        # if the format of padding in incorrect we have to return
        if field.count(DYNAMIC_PREFIX_PADDING_START) > 1 or field.count(DYNAMIC_PREFIX_PADDING_END) > 1:
            return field, 0
        if field.index(DYNAMIC_PREFIX_PADDING_START) > field.index(DYNAMIC_PREFIX_PADDING_END):
            return field, 0
        if field[len(field) - 1] != DYNAMIC_PREFIX_PADDING_END:
            return field, 0
        field = field.replace(DYNAMIC_PREFIX_PADDING_END, "")
        field_padding_tab = field.split(DYNAMIC_PREFIX_PADDING_START)
        try:
            field, padding = field_padding_tab[0], int(field_padding_tab[1])
        except ValueError as va:
            raise ValidationError(_("Padding in field %s must be integer!") % field_padding_tab[0])
        return field, padding

    def _remove_static_fields(self):
        pass

    @api.model
    def _parse_many2one_field(self, record, dynamic_prefix_fields, field):
        prefix = ''
        nested_list_fields = field.split(".")
        next_field = nested_list_fields.pop(0)
        record = self._get_record_from_field_value(record, dynamic_prefix_fields, next_field)
        if not record:
            return False
        while nested_list_fields:
            next_field = nested_list_fields.pop(0)
            val = getattr(record, next_field)
            # Here we have to add this (val != 0) because in python 0 is considered as False
            if not val and val != 0:
                return False
            if isinstance(val, str):
                prefix += val
            elif isinstance(val, int) or isinstance(val, float) or isinstance(val, bool):
                prefix += str(val)
            elif isinstance(val, datetime.date):
                prefix += str(val)
            else:
                record = val
        return prefix

    def _get_record_from_field_value(self, record, dynamic_prefix_fields, field):
        if isinstance(dynamic_prefix_fields[field], int):
            record_obj = self.env[record._fields[field].comodel_name]
            return record_obj.browse(dynamic_prefix_fields[field])
        else:
            return dynamic_prefix_fields[field]
