from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
PROFILE = ROOT / "templates" / "profile.html"
SIDEBAR = ROOT / "templates" / "_app_sidebar.html"

for path in (APP, PROFILE, SIDEBAR):
    if not path.exists():
        raise SystemExit(
            f"ERROR: Missing {path}. Put this installer in D:\\InternShield-AI."
        )

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

for path in (APP, PROFILE, SIDEBAR):
    backup = path.with_name(
        path.name + f".before_profile_storage_{stamp}.bak"
    )
    shutil.copy2(path, backup)
    print("Backup:", backup)


# =========================================================
# app.py
# =========================================================

text = APP.read_text(encoding="utf-8")

if "import uuid\n" not in text:
    text = text.replace(
        "import os\n",
        "import os\nimport uuid\n",
        1,
    )


if 'PROFILE_IMAGE_BUCKET = "profile-images"' not in text:
    marker = "\n\n@app.context_processor\ndef inject_workspace_identity():"

    if marker not in text:
        raise SystemExit(
            "ERROR: Could not find inject_workspace_identity() in app.py."
        )

    helpers = '''

# =========================================================
# PROFILE IMAGE STORAGE
# =========================================================

PROFILE_IMAGE_BUCKET = "profile-images"


def _profile_storage_object_path(image_value):
    value = str(image_value or "").strip()

    marker = (
        "/storage/v1/object/public/"
        + PROFILE_IMAGE_BUCKET
        + "/"
    )

    if marker not in value:
        return ""

    return (
        value
        .split(marker, 1)[1]
        .split("?", 1)[0]
        .strip("/")
    )


def _delete_profile_image_value(
    supabase,
    image_value,
):
    """Delete an old Supabase avatar or legacy local avatar."""

    value = str(image_value or "").strip()

    if not value:
        return

    storage_path = _profile_storage_object_path(value)

    if storage_path:
        try:
            (
                supabase
                .storage
                .from_(PROFILE_IMAGE_BUCKET)
                .remove([storage_path])
            )
        except Exception:
            app.logger.exception(
                "Old Supabase profile image could not be removed"
            )

        return

    if value.startswith(("http://", "https://")):
        return

    legacy_path = os.path.join(
        app.static_folder,
        value,
    )

    if os.path.isfile(legacy_path):
        try:
            os.remove(legacy_path)
        except OSError:
            app.logger.exception(
                "Legacy local profile image could not be removed"
            )
'''

    text = text.replace(
        marker,
        helpers + marker,
        1,
    )


if 'uploaded_storage_path = ""' not in text:
    start_marker = '''            # -------------------------------------------------
            # SAVE / REMOVE PROFILE IMAGE
            # -------------------------------------------------
'''
    end_marker = '''            # -------------------------------------------------
            # DATABASE SAVE
            # -------------------------------------------------
'''

    start = text.find(start_marker)
    end = text.find(end_marker, start)

    if start == -1 or end == -1:
        raise SystemExit(
            "ERROR: Could not locate the existing profile-image save block."
        )

    end += len(end_marker)

    replacement = '''            # -------------------------------------------------
            # SAVE / REMOVE PROFILE IMAGE
            # -------------------------------------------------

            old_profile_image_path = (
                profile_data.get("profile_image_path")
                or ""
            )

            new_profile_image_path = old_profile_image_path
            uploaded_storage_path = ""
            old_image_should_be_deleted = False

            if remove_profile_image:
                new_profile_image_path = ""
                old_image_should_be_deleted = bool(
                    old_profile_image_path
                )

            if (
                uploaded_profile_image
                and uploaded_profile_image.filename
                and image_extension
            ):
                normalized_extension = (
                    ".jpg"
                    if image_extension == ".jpeg"
                    else image_extension
                )

                storage_filename = (
                    "avatar-"
                    + uuid.uuid4().hex
                    + normalized_extension
                )

                storage_object_path = (
                    str(session["user_id"])
                    + "/"
                    + storage_filename
                )

                try:
                    uploaded_profile_image.stream.seek(0)
                    image_bytes = uploaded_profile_image.stream.read()
                    uploaded_profile_image.stream.seek(0)

                    (
                        supabase
                        .storage
                        .from_(PROFILE_IMAGE_BUCKET)
                        .upload(
                            path=storage_object_path,
                            file=image_bytes,
                            file_options={
                                "content-type": (
                                    uploaded_profile_image.mimetype
                                    or "application/octet-stream"
                                ),
                                "cache-control": "3600",
                                "upsert": "false",
                            },
                        )
                    )

                    public_url = (
                        supabase
                        .storage
                        .from_(PROFILE_IMAGE_BUCKET)
                        .get_public_url(storage_object_path)
                    )

                    public_url = str(public_url or "").strip()

                    if not public_url.startswith(("http://", "https://")):
                        raise ValueError(
                            "Supabase returned an invalid public image URL."
                        )

                    uploaded_storage_path = storage_object_path
                    new_profile_image_path = public_url
                    old_image_should_be_deleted = bool(
                        old_profile_image_path
                    )

                except Exception:
                    app.logger.exception(
                        "Profile image upload to Supabase Storage failed"
                    )
                    errors.append(
                        "Your profile photo could not be uploaded. "
                        "Please try again."
                    )

            if errors:
                for message in errors:
                    flash(message, "danger")

            else:
                # -------------------------------------------------
                # DATABASE SAVE
                # -------------------------------------------------
'''

    text = text[:start] + replacement + text[end:]

    # Existing DB-save section now belongs inside the new nested else.
    db_start = text.find(
        "            now_iso = datetime.now(\n",
        text.find('uploaded_storage_path = ""'),
    )
    db_end_marker = (
        "\n    # ---------------------------------------------------------\n"
        "    # ACCOUNT OVERVIEW\n"
    )
    db_end = text.find(db_end_marker, db_start)

    if db_start == -1 or db_end == -1:
        raise SystemExit(
            "ERROR: Could not locate the profile database-save section."
        )

    block = text[db_start:db_end]
    block = "".join(
        ("    " + line if line.strip() else line)
        for line in block.splitlines(keepends=True)
    )
    text = text[:db_start] + block + text[db_end:]


session_anchor = '''                    session[
                        "workspace_profile_loaded"
                    ] = True
'''

session_replacement = '''                    session[
                        "workspace_profile_loaded"
                    ] = True

                    if (
                        old_image_should_be_deleted
                        and old_profile_image_path
                        and old_profile_image_path != new_profile_image_path
                    ):
                        _delete_profile_image_value(
                            supabase,
                            old_profile_image_path,
                        )
'''

if session_replacement not in text:
    start = text.find('uploaded_storage_path = ""')
    pos = text.find(session_anchor, start)

    if pos == -1:
        raise SystemExit(
            "ERROR: Could not locate workspace profile-session update."
        )

    text = text[:pos] + text[pos:].replace(
        session_anchor,
        session_replacement,
        1,
    )


except_anchor = '''                except Exception:
                    app.logger.exception(
                        "User profile could not be saved"
                    )
'''

except_replacement = '''                except Exception:
                    if uploaded_storage_path:
                        try:
                            (
                                supabase
                                .storage
                                .from_(PROFILE_IMAGE_BUCKET)
                                .remove([uploaded_storage_path])
                            )
                        except Exception:
                            app.logger.exception(
                                "Uncommitted profile image rollback failed"
                            )

                    app.logger.exception(
                        "User profile could not be saved"
                    )
'''

if except_replacement not in text:
    start = text.find('uploaded_storage_path = ""')
    pos = text.find(except_anchor, start)

    if pos == -1:
        raise SystemExit(
            "ERROR: Could not locate the profile save exception handler."
        )

    text = text[:pos] + text[pos:].replace(
        except_anchor,
        except_replacement,
        1,
    )


APP.write_text(text, encoding="utf-8")
print("Updated:", APP)


# =========================================================
# templates/profile.html
# =========================================================

profile_text = PROFILE.read_text(encoding="utf-8")

old_profile_src = 'src="{{ url_for(\'static\', filename=image_path) }}"'
new_profile_src = (
    'src="{{ image_path if image_path[:4] == \'http\' '
    'else url_for(\'static\', filename=image_path) }}"'
)

count = profile_text.count(old_profile_src)

if count:
    profile_text = profile_text.replace(
        old_profile_src,
        new_profile_src,
    )
elif new_profile_src not in profile_text:
    raise SystemExit(
        "ERROR: Could not locate profile image URLs in profile.html."
    )

PROFILE.write_text(profile_text, encoding="utf-8")
print("Updated:", PROFILE, f"({count} image URL replacement(s))")


# =========================================================
# templates/_app_sidebar.html
# =========================================================

sidebar_text = SIDEBAR.read_text(encoding="utf-8")

old_sidebar_src = (
    'src="{{ url_for(\'static\', '
    'filename=workspace_profile_image_path) }}"'
)
new_sidebar_src = (
    'src="{{ workspace_profile_image_path '
    'if workspace_profile_image_path[:4] == \'http\' '
    'else url_for(\'static\', '
    'filename=workspace_profile_image_path) }}"'
)

if old_sidebar_src in sidebar_text:
    sidebar_text = sidebar_text.replace(
        old_sidebar_src,
        new_sidebar_src,
    )
elif new_sidebar_src not in sidebar_text:
    raise SystemExit(
        "ERROR: Could not locate sidebar profile image URL."
    )

SIDEBAR.write_text(sidebar_text, encoding="utf-8")
print("Updated:", SIDEBAR)

print()
print("SUCCESS: Supabase profile-image storage upgrade installed.")
print()
print("Next:")
print(r"  python -m py_compile app.py")
print(r"  python app.py")
print()
print(
    "Then open Profile -> Manage profile and upload your photo once. "
    "The new object should appear in Supabase Storage under "
    "profile-images/<your-user-id>/."
)
