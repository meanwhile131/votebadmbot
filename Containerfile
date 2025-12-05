FROM python:3.13-slim
RUN pip install pipenv
WORKDIR /usr/src/app
COPY Pipfile Pipfile.lock ./
RUN pipenv install --deploy --system
COPY src .
CMD ["python", "src/main.py"]