# magma-riscv-mini
![Linux Test](https://github.com/leonardt/magma_riscv_mini/workflows/Linux%20Test/badge.svg)

magma port of https://github.com/ucb-bar/riscv-mini

Currently WIP, please post any questions on GitHub Issues or feel free to
contribute!

## Dependencies
### Ubuntu
```
sudo apt install verilator libgmp-dev libmpfr-dev libmpc-dev
```
### MacOS
```
brew install verilator gmp mpfr libmpc
```

## Test
```
pip install pytest pytest-codestyle
pip install -e .
pytest --pycodestyle tests
```
