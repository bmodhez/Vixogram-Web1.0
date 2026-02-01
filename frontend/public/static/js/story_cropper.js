(function () {
  function fireToast(message, kind) {
    try {
      document.body.dispatchEvent(
        new CustomEvent('vixo:toast', {
          detail: {
            message: message || '',
            kind: kind || 'info',
            durationMs: 4500,
          },
        })
      );
    } catch (e) {}
  }

  function describeUserAgent(ua) {
    const s = String(ua || '').toLowerCase();
    if (!s.trim()) return '';

    let os = '';
    if (s.includes('iphone') || s.includes('ipad') || s.includes('ios')) os = 'iOS';
    else if (s.includes('android')) os = 'Android';
    else if (s.includes('windows')) os = 'Windows';
    else if (s.includes('mac os x') || s.includes('macintosh')) os = 'macOS';
    else if (s.includes('linux')) os = 'Linux';

    let browser = 'Browser';
    if (s.includes('edg/') || s.includes('edge/')) browser = 'Edge';
    else if (s.includes('opr/') || s.includes('opera')) browser = 'Opera';
    else if (s.includes('chrome/') || s.includes('crios')) browser = 'Chrome';
    else if (s.includes('firefox/') || s.includes('fxios')) browser = 'Firefox';
    else if (s.includes('safari/')) browser = 'Safari';

    return os ? `${browser} on ${os}` : browser;
  }

  function initStoryCropper(root) {
    root = root || document;

    const input = root.querySelector('#story_image_input');
    const selectBtn = root.querySelector('#story_select_btn');
    const fileName = root.querySelector('#story_file_name');
    const wrap = root.querySelector('#story_crop_wrap');
    const img = root.querySelector('#story_crop_img');
    const hidden = root.querySelector('#story_cropped_image_data');
    const resetBtn = root.querySelector('#story_reset_crop');
    const form = input && input.closest ? input.closest('form') : null;

    if (!input || !selectBtn || !img || !wrap || !hidden || !form) return;
    if (form.dataset.storyCropperBound === '1') return;
    form.dataset.storyCropperBound = '1';

    let cropper = null;
    let lastObjectUrl = null;

    const destroy = () => {
      try {
        if (cropper) cropper.destroy();
      } catch (e) {}
      cropper = null;
      if (lastObjectUrl) {
        try {
          URL.revokeObjectURL(lastObjectUrl);
        } catch (e) {}
      }
      lastObjectUrl = null;
    };

    selectBtn.addEventListener('click', (e) => {
      e.preventDefault();
      try {
        input.click();
      } catch (err) {}
    });

    input.addEventListener('change', () => {
      hidden.value = '';
      const f = input.files && input.files[0];
      if (!f) {
        if (fileName) fileName.textContent = 'No image selected';
        wrap.classList.add('hidden');
        destroy();
        return;
      }

      if (fileName) fileName.textContent = f.name || 'Selected image';

      destroy();
      const url = URL.createObjectURL(f);
      lastObjectUrl = url;
      img.src = url;
      wrap.classList.remove('hidden');

      const boot = () => {
        if (!window.Cropper) {
          return false;
        }

        try {
          cropper = new window.Cropper(img, {
            viewMode: 1,
            dragMode: 'move',
            aspectRatio: 9 / 16,
            autoCropArea: 1,
            responsive: true,
            background: false,
            movable: true,
            zoomable: true,
            scalable: false,
            rotatable: false,
          });
          return true;
        } catch (e) {
          cropper = null;
          return true;
        }
      };

      try {
        img.onload = () => {
          let tries = 0;
          const tick = () => {
            tries += 1;
            const done = boot();
            if (done) {
              if (!cropper && !window.Cropper) {
                fireToast('Crop tool failed to load. Uploading original image.', 'error');
              }
              return;
            }
            if (tries < 10) setTimeout(tick, 150);
            else fireToast('Crop tool failed to load. Uploading original image.', 'error');
          };
          tick();
        };
      } catch (e) {}
    });

    if (resetBtn) {
      resetBtn.addEventListener('click', (e) => {
        e.preventDefault();
        try {
          cropper && cropper.reset();
        } catch (err) {}
      });
    }

    let submittingCropped = false;

    form.addEventListener(
      'submit',
      async (e) => {
        try {
          if (submittingCropped) {
            submittingCropped = false;
            return;
          }

          const f = input.files && input.files[0];
          if (!f || !cropper || typeof cropper.getCroppedCanvas !== 'function') {
            hidden.value = '';
            return;
          }

          e.preventDefault();
          e.stopPropagation();

          const canvas = cropper.getCroppedCanvas({
            width: 720,
            height: 1280,
            imageSmoothingEnabled: true,
            imageSmoothingQuality: 'high',
          });

          if (!canvas || typeof canvas.toBlob !== 'function') {
            hidden.value = '';
            submittingCropped = true;
            form.requestSubmit();
            return;
          }

          const blob = await new Promise((resolve) => {
            try {
              canvas.toBlob((b) => resolve(b || null), 'image/jpeg', 0.9);
            } catch (err) {
              resolve(null);
            }
          });

          if (blob) {
            try {
              const dt = new DataTransfer();
              const safeName =
                (f.name || 'story')
                  .replace(/\s+/g, '_')
                  .replace(/\.[a-z0-9]+$/i, '') + '.jpg';
              dt.items.add(new File([blob], safeName, { type: blob.type || 'image/jpeg' }));
              input.files = dt.files;
              hidden.value = '';
            } catch (err) {
              try {
                hidden.value = canvas.toDataURL('image/jpeg', 0.85);
              } catch (e2) {
                hidden.value = '';
              }
            }
          } else {
            try {
              hidden.value = canvas.toDataURL('image/jpeg', 0.85);
            } catch (err) {
              hidden.value = '';
            }
          }

          submittingCropped = true;
          form.requestSubmit();
        } catch (err) {
          try {
            hidden.value = '';
          } catch (e2) {}
        }
      },
      true
    );

    try {
      form.dataset.storyCropperUaHint = describeUserAgent(navigator.userAgent || '');
    } catch (e) {}
  }

  function initNow() {
    initStoryCropper(document);

    document.body.addEventListener('htmx:afterSwap', (e) => {
      try {
        if (!e || !e.detail || !e.detail.target) return;
        const t = e.detail.target;
        if (t.id === 'global_modal_root') {
          initStoryCropper(t);
        }
      } catch (err) {}
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNow);
  } else {
    initNow();
  }
})();
