FROM python:3.13-slim

WORKDIR /var/app

# Dependencies
RUN apt-get update && \
    apt-get install -y \
        libblas-dev \
        liblapack-dev \
        liblapacke-dev \
        gfortran \
        gcc \
        g++ && \
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

# Run the migrations upfront because the sqlite database is stored in a file.
RUN python manage.py migrate

# Create media directories
RUN mkdir -p noteshrinker/media/pdf noteshrinker/media/png

# Server
EXPOSE 8000
ENTRYPOINT ["python", "manage.py"]
CMD ["runserver", "0.0.0.0:8000"]
