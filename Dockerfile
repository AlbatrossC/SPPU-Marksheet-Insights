# Use an official Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install poppler-utils and other system dependencies
RUN apt-get update && \
    apt-get install -y poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a working directory
WORKDIR /app

# Copy your application code
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir flask werkzeug

# Expose the port Flask runs on
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
