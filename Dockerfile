FROM python:3.13-slim

# Create non-root user for running the application
# UID 1000 is commonly used for the first user on Linux systems
RUN groupadd -r appuser -g 1000 && \
    useradd -r -u 1000 -g appuser -m -d /home/appuser -s /bin/bash appuser

WORKDIR /var/app

# Dependencies (install as root)
RUN apt-get update && \
    apt-get install -y \
        libblas-dev \
        liblapack-dev \
        liblapacke-dev \
        gfortran \
        gcc \
        g++ \
        poppler-utils && \
    pip install --upgrade pip setuptools wheel && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements_docker.txt ./
RUN pip install --no-cache-dir -r requirements_docker.txt

RUN pip wheel numpy
RUN pip install numpy

RUN pip wheel scipy
RUN pip install scipy

# Project files
COPY . .

# Create media directories and set ownership
RUN mkdir -p noteshrinker/media/pdf noteshrinker/media/png noteshrinker/media/books noteshrinker/media/pictures logs && \
    chown -R appuser:appuser /var/app

# Switch to non-root user
USER appuser

# Run the migrations upfront because the sqlite database is stored in a file.
RUN python manage.py migrate

# Server
EXPOSE 8000
ENTRYPOINT ["python", "manage.py"]
CMD ["runserver", "0.0.0.0:8000"]
