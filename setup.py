from setuptools import setup

install_requires = list(val.strip() for val in open('requirements.txt'))

setup(name='soliscontrol',
      version='0.1.0',
      description='Clients for controlling a Solis Inverter via the Solis API',
      author='Andrew Speakman',
      author_email='andrew@speakman.org.uk',
      url='https://github.com/aspeakman/soliscontrol',
      packages=['soliscontrol'],
      install_requires=install_requires
      )