FROM python:3.9.5-buster

LABEL description="Docker for running a python script to scrape \
                    data from Flightradar24 (depatures of specified \
                    airports)"

WORKDIR /usr/src/app
COPY . . 

#Read packet lists 
RUN apt update

#Install chrome/chromedriver for selenium
RUN apt-get install -yqq unzip
RUN wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/90.0.4430.24/chromedriver_linux64.zip
RUN unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/

RUN apt-get install -y chromium

#Install chrome dependencies
RUN apt-get install -y libglib2.0-0
RUN apt-get install -y libnss3 
RUN apt-get install -y libgconf-2-4 
RUN apt-get install -y libfontconfig1

ENV DISPLAY=:99
ENV POSTPATH=$postpath

RUN pip3 install -r requirements.txt
 
ENTRYPOINT ["python3"]

CMD ["main1.0.py"]
