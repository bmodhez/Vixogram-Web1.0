from django.forms import ModelForm
from django import forms
from django.core.exceptions import ValidationError
from .models import *

class ChatmessageCreateForm(ModelForm):
    class Meta:
        model = GroupMessage
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={
                'placeholder': 'Add message ...',
                'class': 'w-full bg-white/5 text-white border border-white/10 rounded-3xl px-4 pr-24 py-3 leading-6 outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500/30 placeholder:text-gray-400 text-sm sm:text-base placeholder:text-sm sm:placeholder:text-base resize-none break-words whitespace-pre-wrap',
                'maxlength': '300',
                'rows': '1',
                'autofocus': True,
            }),
        }

    def clean_body(self):
        body = (self.cleaned_data.get('body') or '').strip()
        if not body:
            raise ValidationError('Message cannot be empty')
        return body
        
        
class NewGroupForm(ModelForm):
    class Meta:
        model = ChatGroup
        fields = ['groupchat_name']
        widgets = {
            'groupchat_name' : forms.TextInput(attrs={
                'placeholder': 'Add name ...', 
                'class': 'w-full bg-gray-800/70 text-white border border-gray-700 rounded-lg px-4 py-3 outline-none focus:border-emerald-500 placeholder:text-gray-400',
                'maxlength' : '300', 
                'autofocus': True,
                }),
        }
        
        
class ChatRoomEditForm(ModelForm):
    class Meta:
        model = ChatGroup
        fields = ['groupchat_name', 'only_admins_can_send']
        widgets = {
            'groupchat_name' : forms.TextInput(attrs={
                'class': 'w-full bg-gray-800/70 text-white border border-gray-700 rounded-lg px-4 py-3 outline-none focus:border-emerald-500 text-xl font-bold mb-4',
                'maxlength' : '300', 
                }),
            'only_admins_can_send': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-700 bg-gray-900 text-emerald-500 focus:ring-emerald-500',
            }),
        }


class PrivateRoomCreateForm(forms.Form):
    name = forms.CharField(
        required=False,
        max_length=128,
        widget=forms.TextInput(attrs={
            'placeholder': 'Private room name (optional)',
            'class': 'w-full bg-white/5 text-white border border-white/10 rounded-2xl px-3 py-2 outline-none focus:border-indigo-400/30 placeholder:text-gray-400',
        }),
    )


class RoomCodeJoinForm(forms.Form):
    code = forms.CharField(
        required=True,
        max_length=16,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter room code ...',
            'class': 'w-full bg-white/5 text-white border border-white/10 rounded-2xl px-3 py-2 outline-none focus:border-indigo-400/30 placeholder:text-gray-400',
            'autocomplete': 'off',
            'autocapitalize': 'characters',
            'autocorrect': 'off',
            'spellcheck': 'false',
            'inputmode': 'text',
            'enterkeyhint': 'go',
        }),
    )