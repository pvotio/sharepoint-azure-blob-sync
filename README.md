
# Share Point Azure Blob Sync

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Docker](https://img.shields.io/badge/docker-enabled-blue.svg)

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Required Variables](#required-variables)
  - [Example FILENAME_PATTERNS](#example-filename_patterns)
  - [Using a `.env` File (Optional)](#using-a-env-file-optional)
- [Usage](#usage)
  - [Running the Script Locally](#running-the-script-locally)
- [Logging](#logging)
- [Deployment](#deployment)
  - [Building the Docker Image](#building-the-docker-image)
  - [Running the Docker Container Locally](#running-the-docker-container-locally)
  - [Azure DevOps Pipeline](#azure-devops-pipeline)
    - [Define Pipeline Variables](#define-pipeline-variables)
    - [Configure `azure-pipelines.yml`](#configure-azure-pipelinesyml)
    - [Automated Deployment](#automated-deployment)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

## Overview

**SharePointAzureBlobSync** is a Python-based tool designed to synchronize files from a SharePoint site to Azure Blob Storage. The script identifies files in SharePoint, compares their timestamps with existing blobs in Azure, and updates the blobs only if newer versions are available. This ensures that your Azure Blob Storage always contains the most recent versions of your SharePoint files.

## Features

- **Selective Synchronization:** Only uploads files to Azure Blob Storage if they are newer than the existing blobs.
- **Pattern-Based File Matching:** Supports defining specific filename patterns to target particular files.
- **Concurrent Processing:** Utilizes multithreading to handle multiple file uploads/downloads simultaneously.
- **Robust Logging:** Implements detailed logging for monitoring and troubleshooting.
- **Dockerized Deployment:** Easily deployable using Docker, ensuring consistency across environments.
- **Azure DevOps Integration:** Automates the build and deployment process through Azure DevOps pipelines.

## Architecture

1. **SharePoint Source:** The origin of the files to be synchronized.
2. **Azure Blob Storage:** The target storage where files are uploaded.
3. **Python Script:** Handles authentication, file comparison, and synchronization logic.
4. **Docker Container:** Encapsulates the Python environment and dependencies.
5. **Azure DevOps Pipeline:** Automates the build, test, and deployment processes.

## Prerequisites

Before setting up **SharePointAzureBlobSync**, ensure you have the following:

- **Python 3.11** installed locally (for development and testing).
- **Docker** installed on your machine.
- **Kubernetes Cluster** (e.g., Azure Kubernetes Service - AKS) with **Azure Workload Identity** configured.
- Access to the **SharePoint** site with appropriate permissions to read files.
- An **Azure Storage Account** with Blob Storage enabled.
- **Azure Workload Identity** configured in your Kubernetes cluster.
- Necessary **Azure Roles** assigned to the Managed Identity for accessing SharePoint and Azure Blob Storage.

## Installation

### 1. Clone the Repository

\`\`\`bash
git clone https://github.com/yourusername/SharePointAzureBlobSync.git
cd SharePointAzureBlobSync
\`\`\`

## Configuration

### Environment Variables

The application relies on several environment variables for configuration. These variables can be set directly in your environment or managed securely through Docker and Azure DevOps.

### Required Variables

| Variable                        | Description                                                                                             |
| ------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `AZURE_STORAGE_ACCOUNT_NAME`    | Name of your Azure Storage Account.                                                                     |
| `AZURE_BLOB_CONTAINER_NAME`     | Name of the target Azure Blob container.                                                                |
| `FOLDER_PATH`                   | Path to the SharePoint folder to synchronize (e.g., `General/mydocuments`).                             |
| `SITE_URL`                      | URL of the SharePoint site (e.g., `https://xxx.sharepoint.com/sites/mysite`).                           |
| `FILENAME_PATTERNS`             | JSON-formatted string defining filename patterns and target folders.                                    |

### Example FILENAME_PATTERNS

\`\`\`json
[
    {"pattern": "^Filename1_[A-Za-z0-9]{12}\.pdf$", "target_folder": "Foldername1"},
    {"pattern": "^Filename2_[A-Za-z0-9]{12}\.pdf$", "target_folder": "Foldername2"},
    {"pattern": "^Filename3_[A-Za-z0-9]{12}\.pdf$", "target_folder": "Foldername3"}
]
\`\`\`

## Usage

### Running the Script Locally

Ensure that all required environment variables are set either in your environment or via a `.env` file.

\`\`\`bash
python src/your_script.py
\`\`\`

## Logging

The script generates logs in two places:

- **Console Output:** Logs with `INFO` level and above are displayed in the console.
- **Log File:** Detailed logs with `DEBUG` level and above are stored in `download_upload.log` located in the root directory.
- **Log Rotation:** The log file is configured to rotate after reaching 5 MB, keeping up to 5 backup files.

## Contributing

Contributions are welcome! To contribute to **SharePointAzureBlobSync**, follow these steps:

1. **Fork the Repository**
2. **Create a New Branch**

\`\`\`bash
git checkout -b feature/YourFeatureName
\`\`\`

3. **Make Your Changes**
4. **Commit Your Changes**

\`\`\`bash
git commit -m "Add feature XYZ"
\`\`\`

5. **Push to Your Fork**

\`\`\`bash
git push origin feature/YourFeatureName
\`\`\`

6. **Create a Pull Request**

Navigate to the original repository and create a pull request from your fork.

## License

This project is licensed under the MIT License.

## Contact

For any questions or feedback, please contact [clem@arqs.io](mailto:your-email@example.com).
