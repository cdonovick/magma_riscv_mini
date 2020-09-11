import operator
import magma as m

from hwtypes import Bit
from hwtypes import BitVector as BV

from riscv_mini.csr import CSR
import riscv_mini.instructions as Instructions
import riscv_mini.control as Control
from riscv_mini.data_path import Const

def concat(*args):
    x = args[0]
    if isinstance(x, Bit):
        x = BitVector[1](x)
    if len(args) == 1:
        return x
    return x.concat(concat(*args[1:]))


def Valid(T):
    return m.Product.from_fields(f"Valid[{T}]", {
        "bits": T,
        "valid": m.Bit
    })


def HostIO(x_len):
    return m.IO(
        host=m.Product.from_fields("HostIO", {
            "fromhost": m.In(Valid(m.UInt[x_len])),
            "tohost": m.Out(m.UInt[x_len])
        })
    )


class CSRGen(m.Generator2):
    def __init__(self, x_len):
        class Cause:
            InstAddrMisaligned = m.UInt[x_len](0x0)
            IllegalInst = m.UInt[x_len](0x2)
            Breakpoint = m.UInt[x_len](0x3)
            LoadAddrMisaligned = m.UInt[x_len](0x4)
            StoreAddrMisaligned = m.UInt[x_len](0x6)
            Ecall = m.UInt[x_len](0x8)

        self.io = io = m.IO(
            stall=m.In(m.Bit),
            cmd=m.In(m.UInt[3]),
            I=m.In(m.UInt[x_len]),
            O=m.Out(m.UInt[x_len]),
            # Excpetion
            pc=m.In(m.UInt[x_len]),
            addr=m.In(m.UInt[x_len]),
            inst=m.In(m.UInt[x_len]),
            illegal=m.In(m.Bit),
            st_type=m.In(m.UInt[2]),
            ld_type=m.In(m.UInt[3]),
            pc_check=m.In(m.Bit),
            expt=m.Out(m.Bit),
            evec=m.Out(m.UInt[x_len]),
            epc=m.Out(m.UInt[x_len])
        ) + HostIO(x_len) + m.ClockIO()

        csr_addr = io.inst[20:32]
        rs1_addr = io.inst[15:20]

        # user counters
        time = m.Register(m.UInt[x_len])()
        timeh = m.Register(m.UInt[x_len])()
        cycle = m.Register(m.UInt[x_len])()
        cycleh = m.Register(m.UInt[x_len])()
        instret = m.Register(m.UInt[x_len])()
        instreth = m.Register(m.UInt[x_len])()

        mcpuid = concat(BV[2](0),  # RV32I
                        BV[x_len - 28](0),
                        BV[26](1 << (ord('I') - ord('A')) |  # Base ISA
                               1 << (ord('U') - ord('A'))))  # User Mode
        mimpid = BV[x_len](0)
        mhartid = BV[x_len](0)

        # interrupt enable stack
        PRV = m.Register(m.UInt[len(CSR.PRV_M)], init=CSR.PRV_M)()
        PRV1 = m.Register(m.UInt[len(CSR.PRV_M)], init=CSR.PRV_M)()
        PRV2 = BV[2](0)
        PRV3 = BV[2](0)
        IE = m.Register(m.Bit, init=False)()
        IE1 = m.Register(m.Bit, init=False)()
        IE2 = False
        IE3 = False

        # virtualization management field
        VM = BV[5](0)

        # memory privilege
        MPRV = False

        # Extension context status
        XS = BV[2](0)
        FS = BV[2](0)
        SD = BV[1](0)
        mstatus = m.concat(SD, BV[x_len-23](0), VM, MPRV, XS, FS, PRV3, IE3,
                           PRV2, IE2, PRV1.O, IE1.O, PRV.O, IE.O)
        mtvec = BV[x_len](Const.PC_EVEC)
        mtdeleg = BV[x_len](0)

        # interrupt registers
        MTIP = m.Register(m.Bit, init=False)()
        HTIP = False
        STIP = False
        MTIE = m.Register(m.Bit, init=False)()
        HTIE = False
        STIE = False
        MSIP = m.Register(m.Bit, init=False)()
        HSIP = False
        SSIP = False
        MSIE = m.Register(m.Bit, init=False)()
        HSIE = False
        SSIE = False

        mip = m.concat(BV[x_len - 8](0), MTIP.O, HTIP, STIP, Bit(False),
                       MSIP.O, HSIP, SSIP, Bit(False))
        mie = m.concat(BV[x_len - 8](0), MTIE.O, HTIE, STIE, Bit(False),
                       MSIE.O, HSIE, SSIE, Bit(False))

        mtimecmp = m.Register(m.UInt[x_len])()
        mscratch = m.Register(m.UInt[x_len])()

        mepc = m.Register(m.UInt[x_len])()
        mcause = m.Register(m.UInt[x_len])()
        mbadaddr = m.Register(m.UInt[x_len])()

        mtohost = m.Register(m.UInt[x_len])()
        mfromhost = m.Register(m.UInt[x_len])()

        io.host.tohost @= mtohost.O
        csr_file = {
            CSR.cycle: cycle.O,
            CSR.time: time.O,
            CSR.instret: instret.O,
            CSR.cycleh: cycleh.O,
            CSR.timeh: timeh.O,
            CSR.instreth: instreth.O,
            CSR.cyclew: cycle.O,
            CSR.timew: time.O,
            CSR.instretw: instret.O,
            CSR.cyclehw: cycleh.O,
            CSR.timehw: timeh.O,
            CSR.instrethw: instreth.O,
            CSR.mcpuid: mcpuid,
            CSR.mimpid: mimpid,
            CSR.mhartid: mhartid,
            CSR.mtvec: mtvec,
            CSR.mtdeleg: mtdeleg,
            CSR.mie: mie,
            CSR.mtimecmp: mtimecmp.O,
            CSR.mtime: time.O,
            CSR.mtimeh: timeh.O,
            CSR.mscratch: mscratch.O,
            CSR.mepc: mepc.O,
            CSR.mcause: mcause.O,
            CSR.mbadaddr: mbadaddr.O,
            CSR.mip: mip,
            CSR.mtohost: mtohost.O,
            CSR.mfromhost: mfromhost.O,
            CSR.mstatus: mstatus,
        }
        out = m.bits(0, x_len)
        for key, value in reversed(list(csr_file.items())):
            out = m.mux([out, value], csr_addr == key)
        io.O @= out

        priv_valid = csr_addr[8:10] <= PRV.O
        priv_inst = io.cmd == CSR.P
        is_E_call = priv_inst & ~csr_addr[0] & ~csr_addr[8]
        is_E_break = priv_inst & csr_addr[0] & ~csr_addr[8]
        is_E_ret = priv_inst & ~csr_addr[0] & csr_addr[8]
        csr_valid = m.reduce(operator.or_, m.bits([csr_addr == key
                                                   for key in csr_file]))
        csr_RO = (m.reduce(operator.and_, csr_addr[10:12]) |
                  (csr_addr == CSR.mtvec) | (csr_addr == CSR.mtdeleg))
        wen = (io.cmd == CSR.W) | io.cmd[1] & m.reduce(operator.or_, rs1_addr)
        wdata_dict = {
            CSR.W: io.I,
            CSR.S: out | io.I,
            CSR.C: out & ~io.I
        }
        wdata = m.uint(0, x_len)
        for key, value in reversed(list(wdata_dict.items())):
            wdata = m.mux([wdata, value], io.cmd == key)

        iaddr_invalid = io.pc_check & io.addr[1]

        laddr_dict = {
            Control.LD_LW: m.reduce(operator.or_, io.addr[0:1]),
            Control.LD_LH: io.addr[0],
            Control.LD_LHU: io.addr[0]
        }
        laddr_invalid = False
        for key, value in reversed(list(laddr_dict.items())):
            laddr_invalid = m.mux([laddr_invalid, value], io.ld_type == key)

        saddr_dict = {
            Control.ST_SW: m.reduce(operator.or_, io.addr[0:1]),
            Control.ST_SH: io.addr[0]
        }
        saddr_invalid = False
        for key, value in reversed(list(saddr_dict.items())):
            saddr_invalid = m.mux([saddr_invalid, value], io.st_type == key)

        expt = (io.illegal | iaddr_invalid | laddr_invalid | saddr_invalid |
                m.reduce(operator.or_, io.cmd[0:1]) &
                (~csr_valid | ~priv_valid) | wen & csr_RO |
                (priv_inst & ~priv_valid) | is_E_call | is_E_break)
        io.expt @= expt

        io.evec @= mtvec + m.zext_to(PRV.O << 6, x_len)
        io.epc @= mepc.O

        is_inst_ret = ((io.inst != Instructions.NOP) &
                       (~expt | is_E_call | is_E_break) & ~io.stall)

        @m.inline_combinational()
        def logic():
            # Counters
            time.I @= time.O + 1
            timeh.I @= timeh.O
            if m.reduce(operator.and_, time.O):
                timeh.I @= timeh.O + 1

            cycle.I @= cycle.O + 1
            cycleh.I @= cycleh.O
            if m.reduce(operator.and_, cycle.O):
                cycleh.I @= cycleh.O + 1
            instret.I @= instret.O
            if is_inst_ret:
                instret.I @= instret.O + 1
            instreth.I @= instreth.O
            if is_inst_ret & m.reduce(operator.and_, instret.O):
                instreth.I @= instreth.O + 1

            mbadaddr.I @= mbadaddr.O
            mepc.I @= mepc.O
            mcause.I @= mcause.O
            PRV.I @= PRV.O
            IE.I @= IE.O
            IE1.I @= IE1.O
            PRV1.I @= PRV1.O
            MTIP.I @= MTIP.O
            MSIP.I @= MSIP.O
            MTIE.I @= MTIE.O
            MSIE.I @= MSIE.O
            mtimecmp.I @= mtimecmp.O
            mscratch.I @= mscratch.O
            mtohost.I @= mtohost.O
            mfromhost.I @= mfromhost.O
            if io.host.fromhost.valid:
                mfromhost.I @= io.host.fromhost.bits

            if ~io.stall:
                if expt:
                    mepc.I @= io.pc >> 2 << 2
                    if iaddr_invalid:
                        mcause.I @= Cause.InstAddrMisaligned
                    elif laddr_invalid:
                        mcause.I @= Cause.LoadAddrMisaligned
                    elif saddr_invalid:
                        mcause.I @= Cause.StoreAddrMisaligned
                    elif is_E_call:
                        mcause.I @= Cause.Ecall + m.zext_to(PRV.O, x_len)
                    elif is_E_break:
                        mcause.I @= Cause.Breakpoint
                    else:
                        mcause.I @= Cause.IllegalInst
                    PRV.I @= CSR.PRV_M
                    IE.I @= False
                    PRV1.I @= PRV.O
                    IE1.I @= IE.O
                    if iaddr_invalid | laddr_invalid | saddr_invalid:
                        mbadaddr.I @= io.addr
                elif is_E_ret:
                    PRV.I @= PRV1.O
                    IE.I @= IE1.O
                    PRV1.I @= CSR.PRV_U
                    IE1.I @= True
                elif wen:
                    if csr_addr == CSR.mstatus:
                        PRV1.I @= wdata[4:6]
                        IE1.I @= wdata[3]
                        PRV.I @= wdata[1:3]
                        IE.I @= wdata[0]
                    elif csr_addr == CSR.mip:
                        MTIP.I @= wdata[7]
                        MSIP.I @= wdata[3]
                    elif csr_addr == CSR.mie:
                        MTIE.I @= wdata[7]
                        MSIE.I @= wdata[3]
                    elif csr_addr == CSR.mtime:
                        time.I @= wdata
                    elif csr_addr == CSR.mtimeh:
                        timeh.I @= wdata
                    elif csr_addr == CSR.mtimecmp:
                        mtimecmp.I @= wdata
                    elif csr_addr == CSR.mscratch:
                        mscratch.I @= wdata
                    elif csr_addr == CSR.mepc:
                        mepc.I @= wdata >> 2 << 2
                    elif csr_addr == CSR.mcause:
                        mcause.I @= wdata & (1 << (x_len - 1) | 0xf)
                    elif csr_addr == CSR.mbadaddr:
                        mbadaddr.I @= wdata
                    elif csr_addr == CSR.mtohost:
                        mtohost.I @= wdata
                    elif csr_addr == CSR.mfromhost:
                        mfromhost.I @= wdata
                    elif csr_addr == CSR.cyclew:
                        cycle.I @= wdata
                    elif csr_addr == CSR.timew:
                        time.I @= wdata
                    elif csr_addr == CSR.instretw:
                        instret.I @= wdata
                    elif csr_addr == CSR.cyclehw:
                        cycleh.I @= wdata
                    elif csr_addr == CSR.timehw:
                        timeh.I @= wdata
                    elif csr_addr == CSR.instrethw:
                        instret.I @= wdata
