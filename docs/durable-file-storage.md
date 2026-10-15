# Durable storage for worksheet, summary, and concept-map files

Render's web-service filesystem is temporary unless persistent storage is attached. The platform therefore supports an S3-compatible bucket for uploaded worksheets, answer keys, lesson summaries, and uploaded concept-map files. Generated concept maps can be downloaded as SVG files without a stored upload.

## Configure the bucket

Create a private bucket with an S3-compatible provider (for example, Cloudflare R2 or AWS S3), then add these environment variables to the Render web service. Do not commit access keys to GitHub.

- `S3_BUCKET`: bucket name.
- `S3_ACCESS_KEY_ID`: bucket access key.
- `S3_SECRET_ACCESS_KEY`: bucket secret.
- `S3_ENDPOINT_URL`: provider endpoint; for AWS S3, leave this unset.
- `S3_REGION`: provider region. For Cloudflare R2, use `auto`; for AWS S3, use the bucket's actual region.

The same variables must be available in the local project environment when migrating existing files. The bucket should remain private; the application reads files server-side after checking the logged-in user's access and the resource's publication/download permissions.

## Migrate existing local uploads

From the project root on a machine that still has the original `uploads/` files, configure the variables above in the local `.env` file and run:

```powershell
python scripts/migrate_uploads_to_object_storage.py
```

The script uploads files using their relative paths (for example, `worksheets/<uuid>.pdf`) and does not delete or modify local files. Review the final uploaded/failed counts. Then add the same storage settings to Render and deploy the code.

If an old upload is missing both from Render and from every local backup, it cannot be reconstructed from its database record alone; re-upload the original file through the teacher/admin interface.

## Local development

If no `S3_*` settings are present, the application continues to use local `uploads/` storage for development. Local uploads are not durable on Render's default ephemeral filesystem.
