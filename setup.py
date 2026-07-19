from setuptools import setup, find_packages

setup(
    name="clone-hero-converter",
    version="1.2.0",
    description="Convierte MP3/vídeo en charts jugables de Clone Hero",
    author="Marc Valsera",
    url="https://github.com/marcvalsera76-dotcom/clonador",
    packages=find_packages(),
    install_requires=[
        "numpy>=1.24",
        "librosa>=0.10",
        "soundfile>=0.12",
        "static-ffmpeg>=2.5",
        "tqdm>=4.60",
    ],
    entry_points={
        "console_scripts": [
            "clone-hero-converter=clone_hero_converter.cli:main"
        ]
    },
    python_requires=">=3.9",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
    ],
)
