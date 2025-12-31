from django.db import models
from django.contrib.auth.models import User

import base64

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='avatars/', null=True, blank=True)
    displayname = models.CharField(max_length=20, null=True, blank=True)
    info = models.TextField(null=True, blank=True) 
    chat_blocked = models.BooleanField(default=False)
    
    def __str__(self):
        return str(self.user)

    @property
    def name(self):
        if self.displayname:
            return self.displayname
        return self.user.username 

    # Iska gap (indent) ab sahi hai, ye 'name' ke barabar hona chahiye
    @property
    def avatar(self):
        if self.image:
            try:
                return self.image.url
            except Exception:
                # If storage isn't configured or the file is missing, fall back to default.
                pass
        return DEFAULT_AVATAR_DATA_URI


_DEFAULT_AVATAR_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 128 128' role='img' aria-label='User avatar'>
<circle cx='64' cy='64' r='60' fill='#4B5563'/>
<circle cx='64' cy='52' r='20' fill='#F3F4F6'/>
<path d='M24 112c6-24 26-36 40-36s34 12 40 36' fill='#F3F4F6'/>
</svg>"""

DEFAULT_AVATAR_DATA_URI = (
    "data:image/svg+xml;base64," + base64.b64encode(_DEFAULT_AVATAR_SVG.encode("utf-8")).decode("ascii")
)