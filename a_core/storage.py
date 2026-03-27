from __future__ import annotations

import os

from django.conf import settings

import cloudinary.uploader
import cloudinary.exceptions
from cloudinary_storage.storage import MediaCloudinaryStorage


class ModeratedMediaCloudinaryStorage(MediaCloudinaryStorage):
    """Cloudinary storage with server-side moderation enabled on upload.

    Uses Cloudinary's built-in moderation add-on during upload.

    Default moderation provider: AWS Rekognition ("aws_rek").
    Override via env var: CLOUDINARY_UPLOAD_MODERATION.
    """

    def _upload(self, name, content):
        options = {
            'use_filename': True,
            'unique_filename': False,
            'overwrite': True,
            'invalidate': True,
            'resource_type': self._get_resource_type(name),
            'tags': self.TAG,
        }

        folder = os.path.dirname(name)
        if folder:
            options['folder'] = folder

        moderation = (getattr(settings, 'CLOUDINARY_UPLOAD_MODERATION', None) or '').strip()

        # Cloudinary moderation is optional. Only request it when the account
        # actually has the configured moderation add-on enabled.
        if moderation:
            options['moderation'] = moderation

        # Auto compression + format optimisation (images only).
        # quality="auto:eco"  → Cloudinary picks lowest quality that still looks good
        # fetch_format="auto" → serves WebP/AVIF to browsers that support it
        # Videos are excluded: quality/fetch_format behave differently for them.
        if options.get('resource_type') == 'image':
            options['quality'] = 'auto:eco'
            options['fetch_format'] = 'auto'

        try:
            response = cloudinary.uploader.upload(content, **options)
        except cloudinary.exceptions.AuthorizationRequired as exc:
            raise ValueError('Cloudinary credentials are invalid. Please verify CLOUD_NAME/API_KEY/API_SECRET.') from exc
        except cloudinary.exceptions.Error as exc:
            raise ValueError(f'Cloudinary upload failed: {exc}') from exc

        # Enforce "before save" semantics: don't accept assets until moderation approves.
        # Cloudinary typically returns: { moderation: [{ kind, status, ... }, ...] }
        status = None
        try:
            moderation_info = response.get('moderation')
            if isinstance(moderation_info, list) and moderation_info:
                first = moderation_info[0] if isinstance(moderation_info[0], dict) else None
                if first:
                    status = first.get('status') or first.get('moderation_status') or first.get('state')
            elif isinstance(moderation_info, dict):
                status = moderation_info.get('status') or moderation_info.get('moderation_status') or moderation_info.get('state')
        except Exception:
            status = None

        status = (str(status).lower().strip() if status is not None else None)
        block_pending = bool(getattr(settings, 'CLOUDINARY_UPLOAD_BLOCK_PENDING', True))

        if not moderation:
            return response

        if status in {'rejected', 'failed'}:
            # Cleanup: remove the uploaded asset so it doesn't linger.
            try:
                public_id = response.get('public_id')
                if public_id:
                    cloudinary.uploader.destroy(public_id, invalidate=True, resource_type=self._get_resource_type(name))
            except Exception:
                pass
            raise ValueError('Upload rejected by Vixogram Team')

        if block_pending and status in {'pending', 'in_progress', 'review'}:
            raise ValueError('Upload is under review')

        return response
