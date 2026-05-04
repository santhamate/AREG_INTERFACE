type CommandRow = {
  category: string;
  command: string;
  longName: string;
  description: string;
  example: string;
  notes: string;
};

const rows: CommandRow[] = [
  { category: "LAN interface messages", command: "&ABO", longName: "Abort", description: "Aborts processing of the received commands.", example: "", notes: "Interface message for LAN/serial-like links." },
  { category: "LAN interface messages", command: "&DCL", longName: "Device clear", description: "Aborts processing of the received commands and sets the command-processing software to a defined initial state. Does not change the instrument settings.", example: "", notes: "Interface message for LAN/serial-like links." },
  { category: "LAN interface messages", command: "&GTL", longName: "Go to local", description: "Switches the instrument to local/manual control. The instrument automatically returns to remote state when a remote command is sent, unless &NREN was sent before.", example: "", notes: "Interface message for LAN/serial-like links." },
  { category: "LAN interface messages", command: "&GTR", longName: "Go to remote", description: "Enables automatic transition from local state to remote state by a subsequent remote command, after &NREN was sent.", example: "", notes: "Interface message for LAN/serial-like links." },
  { category: "LAN interface messages", command: "&GET", longName: "Group execute trigger", description: "Triggers a previously active instrument function, for example a sweep. Equivalent to a pulse at the external trigger input.", example: "", notes: "Interface message for LAN/serial-like links." },
  { category: "LAN interface messages", command: "&LLO", longName: "Local lockout", description: "Disables switching from remote control to manual control via the front-panel keys.", example: "", notes: "Interface message for LAN/serial-like links." },
  { category: "LAN interface messages", command: "&NREN", longName: "Not remote enable", description: "Disables automatic transition from local state to remote state by a subsequent remote command. Use &GTR to reactivate automatic transition.", example: "", notes: "Interface message for LAN/serial-like links." },
  { category: "LAN interface messages", command: "&POL", longName: "Serial poll", description: "Starts a serial poll.", example: "", notes: "Interface message for LAN/serial-like links." },

  { category: "LAN protocol connection information", command: "VXI-11", longName: "", description: "LAN protocol using ONC RPC over TCP/IP. Uses TCP/UDP port 111 plus RPC-assigned TCP ports.", example: "", notes: "Connection information, not a SCPI command." },
  { category: "LAN protocol connection information", command: "HiSLIP", longName: "", description: "High-speed LAN instrument protocol. Uses TCP port 4880.", example: "", notes: "Connection information, not a SCPI command." },
  { category: "LAN protocol connection information", command: "Raw socket", longName: "", description: "Simple socket-based SCPI communication. Typically uses TCP port 5025 or 5125.", example: "", notes: "Connection information, not a SCPI command." },
  { category: "LAN protocol connection information", command: "RSIB", longName: "", description: "Deprecated Rohde & Schwarz TCP/IP remote-control protocol. Typically uses TCP port 2525.", example: "", notes: "Connection information, not a SCPI command." },
  { category: "LAN protocol connection information", command: "mDNS / Bonjour / LXI", longName: "", description: "Discovery/browser-related LAN service. Uses TCP port 5353.", example: "", notes: "Connection information, not a SCPI command." },

  { category: "VISA API functions", command: "viOpen()", longName: "", description: "Opens a VISA session with the instrument.", example: "", notes: "API call, not SCPI." },
  { category: "VISA API functions", command: "viWrite()", longName: "", description: "Writes data or SCPI commands to the instrument.", example: "", notes: "API call, not SCPI." },
  { category: "VISA API functions", command: "viReadSTB()", longName: "", description: "Reads the instrument status byte register.", example: "", notes: "API call, not SCPI." },
  { category: "VISA API functions", command: "viRead()", longName: "", description: "Reads the output buffer or instrument response.", example: "", notes: "API call, not SCPI." },
  { category: "VISA API functions", command: "viWaitOnEvent()", longName: "", description: "Waits for a specified VISA event.", example: "", notes: "API call, not SCPI." },
  { category: "VISA API functions", command: "viEnableEvent()", longName: "", description: "Enables VISA event notification, for example service request events.", example: "", notes: "API call, not SCPI." },
  { category: "VISA API functions", command: "viDiscardEvents()", longName: "", description: "Discards stale or queued VISA events.", example: "", notes: "API call, not SCPI." },

  { category: "RSIB library functions", command: "RSDLLibfind()", longName: "", description: "Provides access to an instrument.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibwrt()", longName: "", description: "Sends a zero-terminated string to an instrument.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLilwrt()", longName: "", description: "Sends a defined number of bytes to an instrument.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibwrtf()", longName: "", description: "Sends the contents of a file to an instrument.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibrd()", longName: "", description: "Reads data from an instrument into a string.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLilrd()", longName: "", description: "Reads a defined number of bytes from an instrument.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibrdf()", longName: "", description: "Reads data from an instrument into a file.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibtmo()", longName: "", description: "Sets timeout for RSIB functions.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibsre()", longName: "", description: "Switches an instrument to local or remote state.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibloc()", longName: "", description: "Temporarily switches an instrument to local state.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibeot()", longName: "", description: "Enables or disables the END message for write operations.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibrsp()", longName: "", description: "Performs a serial poll and returns the status byte.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLibonl()", longName: "", description: "Sets the instrument online or offline.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLTestSrq()", longName: "", description: "Checks whether the instrument generated a service request.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLWaitSrq()", longName: "", description: "Waits until the instrument generates a service request.", example: "", notes: "Deprecated library function." },
  { category: "RSIB library functions", command: "RSDLLSwapBytes", longName: "", description: "Swaps byte order for binary numeric display. Only needed on non-Intel platforms.", example: "", notes: "Deprecated library function." },

  { category: "GPIB universal interface commands", command: "DCL", longName: "Device clear", description: "Aborts processing of received commands and resets the command-processing software to a defined initial state. Does not change instrument settings.", example: "", notes: "Universal GPIB interface command." },
  { category: "GPIB universal interface commands", command: "IFC", longName: "Interface clear", description: "Resets interfaces to their default setting.", example: "", notes: "Universal GPIB interface command." },
  { category: "GPIB universal interface commands", command: "LLO", longName: "Local lockout", description: "Disables the Local softkey. Manual operation is unavailable until GTL is executed.", example: "", notes: "Universal GPIB interface command." },
  { category: "GPIB universal interface commands", command: "SPE", longName: "Serial poll enable", description: "Makes the instrument ready for serial poll.", example: "", notes: "Universal GPIB interface command." },
  { category: "GPIB universal interface commands", command: "SPD", longName: "Serial poll disable", description: "Ends serial poll.", example: "", notes: "Universal GPIB interface command." },
  { category: "GPIB universal interface commands", command: "PPU", longName: "Parallel poll unconfigure", description: "Ends the parallel poll state.", example: "", notes: "Universal GPIB interface command." },

  { category: "GPIB addressed interface commands", command: "GET", longName: "Group execute trigger", description: "Triggers a previously active instrument function, for example a sweep.", example: "", notes: "Addressed GPIB command." },
  { category: "GPIB addressed interface commands", command: "GTL", longName: "Go to local", description: "Switches the instrument to local/manual control.", example: "", notes: "Addressed GPIB command." },
  { category: "GPIB addressed interface commands", command: "GTR", longName: "Go to remote", description: "Switches the instrument to remote-control state.", example: "", notes: "Addressed GPIB command." },
  { category: "GPIB addressed interface commands", command: "REN", longName: "Remote enable", description: "Enables transition to remote-control state.", example: "", notes: "Addressed GPIB command." },
  { category: "GPIB addressed interface commands", command: "PPC", longName: "Parallel poll configure", description: "Configures the instrument for parallel poll.", example: "", notes: "Addressed GPIB command." },
  { category: "GPIB addressed interface commands", command: "SDC", longName: "Selected device clear", description: "Aborts processing of received commands and resets command-processing software to a defined initial state. Does not change instrument settings.", example: "", notes: "Addressed GPIB command." },

  { category: "Common SCPI commands", command: "*RST", longName: "Reset", description: "Resets the instrument.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*CLS", longName: "Clear status", description: "Clears status registers and queues.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*ESE", longName: "Standard Event Status Enable", description: "Sets the Standard Event Status Enable register.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*ESE?", longName: "Standard Event Status Enable Query", description: "Queries the Standard Event Status Enable register.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*ESR?", longName: "Standard Event Status Register Query", description: "Queries and clears the Standard Event Status Register.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*IDN?", longName: "Identification Query", description: "Queries the instrument identification string.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*STB?", longName: "Status Byte Query", description: "Queries the status byte register.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*SRE", longName: "Service Request Enable", description: "Sets the Service Request Enable register.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*SRE?", longName: "Service Request Enable Query", description: "Queries the Service Request Enable register.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*IST?", longName: "Individual Status Query", description: "Queries the Individual Status flag.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*PRE", longName: "Parallel Poll Enable", description: "Sets the Parallel Poll Enable register.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*PRE?", longName: "Parallel Poll Enable Query", description: "Queries the Parallel Poll Enable register.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*OPC", longName: "Operation Complete", description: "Sets the Operation Complete bit in the Standard Event Status Register after all previous commands have finished.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*OPC?", longName: "Operation Complete Query", description: "Waits until all previous operations are complete, then returns 1.", example: "", notes: "Common IEEE 488.2 command." },
  { category: "Common SCPI commands", command: "*WAI", longName: "Wait to Continue", description: "Holds further command processing until all commands sent before *WAI have been executed.", example: "", notes: "Common IEEE 488.2 command." },

  { category: "Status and error commands", command: "SYST:ERR?", longName: "System Error Query", description: 'Queries the newest error from the error queue and clears that entry. If no error exists, the instrument returns 0, "No error".', example: "", notes: "Instrument-specific availability may vary." },
  { category: "Status and error commands", command: "SYST:ERR:NEXT?", longName: "System Error Next Query", description: "Queries the next/newest error from the error queue.", example: "", notes: "Instrument-specific availability may vary." },
  { category: "Status and error commands", command: "SYST:ERR:ALL?", longName: "System Error All Query", description: "Queries all errors in the error queue.", example: "", notes: "Instrument-specific availability may vary." },
  { category: "Status and error commands", command: "STAT:OPER...", longName: "Operation status", description: "Queries or configures operation-status registers. Exact subcommands are instrument-specific.", example: "", notes: "Instrument-specific availability may vary." },
  { category: "Status and error commands", command: "STAT:OPER?", longName: "Operation status query", description: "Queries operation-status information.", example: "", notes: "Instrument-specific availability may vary." },
  { category: "Status and error commands", command: "STAT:QUES...", longName: "Questionable status", description: "Queries or configures questionable-status registers. Exact subcommands are instrument-specific.", example: "", notes: "Instrument-specific availability may vary." },
  { category: "Status and error commands", command: "STAT:QUES?", longName: "Questionable status query", description: "Queries questionable-status information.", example: "", notes: "Instrument-specific availability may vary." },

  { category: "Example instrument-specific SCPI commands", command: "DISPlay[:WINDow<1...4>]:MAXimize <Boolean>", longName: "Display maximize", description: "Maximizes or unmaximizes a display window.", example: "DISP:WIND2:MAX ON", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "FORMat:READings:DATA <type>[,<length>]", longName: "Format readings data", description: "Sets reading data format/type and optional length.", example: "", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "HCOPy:DEVice:COLor <Boolean>", longName: "Hardcopy device color", description: "Enables or disables color hardcopy output.", example: "HCOP:DEV:COL ON", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "HCOPy:DEVice:CMAP:COLor:RGB <red>,<green>,<blue>", longName: "Hardcopy device color map RGB", description: "Sets RGB color-map values for hardcopy/device output.", example: "", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "HCOPy[:IMMediate]", longName: "Hardcopy immediate", description: "Starts hardcopy immediately.", example: "HCOP or HCOP:IMM", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "HCOPy:ITEM:ALL", longName: "Hardcopy item all", description: "Selects all hardcopy items.", example: "HCOP:ITEM ALL", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "HCOPy:ITEM:LABel <string>", longName: "Hardcopy item label", description: "Sets a hardcopy label string.", example: "HCOP:ITEM:LABel \"Test1\"", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "HCOPy:PAGE:DIMensions:QUADrant<n>", longName: "Hardcopy page dimensions quadrant", description: "Selects a page-dimension quadrant by numeric suffix.", example: "HCOP:PAGE:DIM:QUAD2", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "HCOPy:PAGE:ORIentation LANDscape | PORTrait", longName: "Hardcopy page orientation", description: "Sets or queries hardcopy page orientation.", example: "HCOP:PAGE:ORI LAND", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "HCOPy:PAGE:SCALe <numeric value>", longName: "Hardcopy page scale", description: "Sets hardcopy page scaling.", example: "HCOP:PAGE:SCAL 90PCT", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "MMEMory:COPY <file_source>,<file_destination>", longName: "Memory copy", description: "Copies a file from source to destination.", example: "MMEM:COPY \"Test1\",\"MeasurementXY\"", notes: "Instrument-specific availability may vary." },
  { category: "Example instrument-specific SCPI commands", command: "SENSE:BANDwidth|BWIDth[:RESolution] <numeric_value>", longName: "Sense bandwidth resolution", description: "Sets resolution bandwidth. BANDwidth and BWIDth are alternative mnemonics with the same effect.", example: "SENS:BAND:RES 1", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "SENSe:FREQuency:STOP <numeric value>", longName: "Sense frequency stop", description: "Sets or queries stop frequency.", example: "SENS:FREQ:STOP 1.5E6", notes: "Example-only command; not guaranteed on every instrument." },
  { category: "Example instrument-specific SCPI commands", command: "SENSe:LIST:FREQuency <numeric_value>{,<numeric_value>}", longName: "Sense list frequency", description: "Sets or queries a frequency list.", example: "SENS:LIST:FREQ 10,20,30,40", notes: "Example-only command; not guaranteed on every instrument." },

  { category: "Invalid/test commands shown in examples", command: "NONSENSE:FOO?", longName: "", description: "Intentionally invalid command used to demonstrate error handling.", example: "", notes: "Example-only invalid command." },
  { category: "Invalid/test commands shown in examples", command: "*NONSENSE?", longName: "", description: "Intentionally invalid common-command query used to demonstrate error handling.", example: "", notes: "Example-only invalid command." },

  { category: "Recommended minimal raw socket test", command: "*IDN?", longName: "Identification Query", description: "Check communication and read instrument identity.", example: "", notes: "Recommended smoke test." },
  { category: "Recommended minimal raw socket test", command: "*CLS", longName: "Clear status", description: "Clear status and error queues.", example: "", notes: "Recommended smoke test." },
  { category: "Recommended minimal raw socket test", command: "SYST:ERR?", longName: "System Error Query", description: "Check whether an error is present.", example: "", notes: "Recommended smoke test." },
  { category: "Recommended minimal raw socket test", command: "*RST;*CLS;*OPC?", longName: "Reset and wait", description: "Reset instrument, clear status, wait until complete.", example: "", notes: "Recommended smoke test." }
];

function notesFor(row: CommandRow): string {
  if (row.notes) {
    return row.notes;
  }
  return row.command.includes("?") ? "Query command." : "Write/action command.";
}

export default function CommandReferenceTable() {
  return (
    <section className="panel">
      <h2>Command Reference</h2>
      <p className="muted small">
        Clean reference table built from the provided inventory. Example-only commands and instrument-specific commands are flagged in Notes.
      </p>

      <div className="table-wrap">
        <table className="reference-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Command</th>
              <th>Long name</th>
              <th>Description</th>
              <th>Example</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.category}-${row.command}`}>
                <td>{row.category}</td>
                <td>{row.command}</td>
                <td>{row.longName || "-"}</td>
                <td>{row.description}</td>
                <td>{row.example || "-"}</td>
                <td>{notesFor(row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}