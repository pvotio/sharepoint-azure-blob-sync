# Use an official Python runtime as a parent image
FROM python:3.13.6-slim-bullseye

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
ENV AZURE_STORAGE_ACCOUNT_NAME=""
ENV AZURE_BLOB_CONTAINER_NAME=""
ENV FOLDER_PATH=""
ENV SITE_URL=""
ENV FILENAME_PATTERNS="[]"

# Expose port if necessary (optional)
# EXPOSE 8000

# Define entry point
CMD ["python", "src/your_script.py"]
