from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm

class LoginForm(forms.Form):
    email = forms.CharField(max_length=50)
    password = forms.CharField(widget=forms.PasswordInput)

class LogupForm(forms.Form):
    username = forms.CharField(max_length=50, required=True)
    email = forms.EmailField(max_length=100, required=True)
    password = forms.CharField(widget=forms.PasswordInput, required=True)

class SearchForm(forms.Form):
    query = forms.CharField(max_length=100, required=False)

class PasswordChangeCustomForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput, label="Mật khẩu cũ")
    new_password = forms.CharField(widget=forms.PasswordInput, label="Mật khẩu mới")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Xác nhận mật khẩu mới")

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password != confirm_password:
            raise ValidationError("Mật khẩu mới và xác nhận mật khẩu không khớp.")

        return cleaned_data