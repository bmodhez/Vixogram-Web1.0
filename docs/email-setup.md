# Email setup (Django-allauth)

## Why “Re-send verification” doesn’t reach inbox in dev
In `ENVIRONMENT=development`, if `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` are NOT set, this project defaults to:

- `EMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend`
- Emails are written to the `tmp_emails/` folder

So the resend action **does generate the email**, but it is saved as a file instead of being delivered.

## Option A: Use real SMTP (recommended)
1. Create a `.env` file (copy from `.env.example`).
2. Set:
   - `EMAIL_HOST_USER`
   - `EMAIL_HOST_PASSWORD`

### Gmail notes
- Turn on 2‑Step Verification
- Create an **App Password** and use it as `EMAIL_HOST_PASSWORD`

Restart the Django server after changing env vars.

## Option B: Keep file-based emails (dev)
After clicking "Re-send verification", open the latest file under:

- `tmp_emails/`

It contains the confirmation link.

## Quick sanity check
- `python manage.py check_env` (shows computed email backend)
- `python manage.py sendtestemail you@example.com` (writes an email using the configured backend)
- `python manage.py send_test_email you@example.com` (project command; available after adding `a_core` to `INSTALLED_APPS`)
