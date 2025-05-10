from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField, TimeField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, ValidationError
import datetime

class LoginForm(FlaskForm):
    """Form for admin login"""
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class APIKeyForm(FlaskForm):
    """Form for creating and editing API keys"""
    owner_name = StringField('Owner Name', validators=[DataRequired()], 
                             render_kw={"placeholder": "Enter the owner name"})
    
    expiry_date = DateField('Expiry Date', validators=[DataRequired()],
                           default=datetime.date.today() + datetime.timedelta(days=30),
                           format='%Y-%m-%d')
    
    hit_limit = IntegerField('Hit Limit', validators=[DataRequired()], default=1000,
                            render_kw={"placeholder": "Enter hit limit (minimum 1)"})
    
    allowed_origins = StringField('Allowed Origins', render_kw={"placeholder": "Enter allowed origins (space-separated)"})
    
    submit = SubmitField('Save')
    
    def validate_hit_limit(self, field):
        if field.data < 1:
            raise ValidationError('Hit limit must be at least 1')

class ChangePasswordForm(FlaskForm):
    """Form for changing admin password"""
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Change Password')
    
    def validate_confirm_password(self, field):
        if field.data != self.new_password.data:
            raise ValidationError('Passwords do not match')
