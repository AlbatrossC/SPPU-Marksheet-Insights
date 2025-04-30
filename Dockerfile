# Base image with Python
FROM python:3.11-slim

# Install Poppler for pdftotext
RUN apt-get update && \
    apt-get install -y poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (if you have a requirements.txt)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app code
COPY . .

# Expose the Flask port
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=production

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
