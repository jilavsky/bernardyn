# Bernardyn

Scientific data analysis and visualization tool built with Python, PySide6, and PyQtGraph.

## Features

- HDF5 data loading and manipulation
- Interactive data visualization with PyQtGraph
- Modern GUI built with PySide6 (Qt6)
- Extensible architecture for future modules

## Installation

### From PyPI (when available)

```bash
pip install Bernardyn
```

### From source

```bash
git clone https://github.com/jilavsky/Bernardyn.git
cd Bernardyn
pip install -e .
```

### Conda environment

```bash
conda create -n bernardyn python=3.12
conda activate bernardyn
pip install -r requirements.txt
```

## Usage

```bash
python -m bernardyn.main
```

Or import as a library:

```python
import bernardyn
print(bernardyn.__version__)
```

## Development

### Setting up the development environment

```bash
pip install -e ".[dev]"
```

### Running tests

```bash
pytest tests/
```

### Code formatting

```bash
black bernardyn/ tests/
ruff check bernardyn/ tests/
```

## License

MIT
