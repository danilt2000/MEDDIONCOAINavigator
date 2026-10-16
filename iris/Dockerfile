FROM intersystems/irishealth-community:latest-cd

WORKDIR /home/irisowner/setup
COPY --chown=irisowner:irisowner merge.cpf setup.script ./

RUN iris start IRIS && \
    iris merge IRIS merge.cpf && \
    iris session IRIS -U %SYS < setup.script && \
    iris stop IRIS quietly
