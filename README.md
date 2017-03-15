`c4.2xlarge`

```
sudo add-apt-repository ppa:jonathonf/python-3.6
sudo apt-get update
sudo apt-get install python3.6
sudo apt-get install python3.6-venv
sudo apt-get install apache2-utils

python3.6 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python fib.py &
ab -c 10 -n 100000 http://0.0.0.0:8080/fib/evensum/1000
```

[ab output](ab.txt)
