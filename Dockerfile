# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project files
COPY src/ ./src/

# Set environment variables (can be overridden at runtime)
ENV TENANT=""
ENV SHAREPOINT_CLIENT_ID=""
ENV SHAREPOINT_CLIENT_SECRET=""
ENV AZURE_STORAGE_CONNECTION_STRING=""
ENV AZURE_BLOB_CONTAINER_NAME=""
ENV FOLDER_PATH=""
ENV SITE_URL=""
ENV FILENAME_PATTERNS="[]"

# Expose port if necessary (optional)
# EXPOSE 8000

# Define entry point
CMD ["python", "src/main.py"]
