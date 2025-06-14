FROM rabbitmq:3-management

RUN rabbitmq-plugins enable --offline rabbitmq_mqtt rabbitmq_federation_management rabbitmq_stomp

ENV RABBITMQ_DEFAULT_USER=user

ENV RABBITMQ_DEFAULT_PASS=password

ENV RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS="+sbwt none +sbwtdcpu none +sbwtdio none"

ENV RABBITMQ_DEFAULT_VHOST="/"

EXPOSE 5672 15672
