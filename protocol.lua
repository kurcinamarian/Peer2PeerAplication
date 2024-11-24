myprotocol = Proto("myprotocol", "M. Kurcina's Protocol")

-- fields definitions
-- flags
local f_flags = ProtoField.string("myprotocol.flags", "Flags (Type)")
local f_flag_handshake = ProtoField.bool("myprotocol.flags.handshake", "Handshake", 8, nil, 0x80)
local f_flag_exit = ProtoField.bool("myprotocol.flags.exit", "Exit", 8, nil, 0x40)
local f_flag_keepalive = ProtoField.bool("myprotocol.flags.keepalive", "Keepalive", 8, nil, 0x20)
local f_flag_data = ProtoField.bool("myprotocol.flags.data", "Data", 8, nil, 0x10)
local f_flag_ack = ProtoField.bool("myprotocol.flags.ack", "Acknowledgment", 8, nil, 0x08)
local f_flag_req = ProtoField.bool("myprotocol.flags.req", "Request", 8, nil, 0x04)
local f_flag_msg = ProtoField.bool("myprotocol.flags.msg", "Message", 8, nil, 0x02)
local f_flag_additional = ProtoField.bool("myprotocol.flags.additional", "Additional Flag", 8, nil, 0x01)
-- other fields
local f_frag_num = ProtoField.uint32("myprotocol.fragment_number", "Fragment Number", base.DEC)
local f_window_size = ProtoField.uint16("myprotocol.window_size", "Window Size", base.DEC)
local f_checksum = ProtoField.uint16("myprotocol.checksum", "Checksum", base.DEC)
local f_data = ProtoField.string("myprotocol.data", "Data")

myprotocol.fields = {
    f_flags, f_flag_handshake, f_flag_exit, f_flag_keepalive, f_flag_data,
    f_flag_ack, f_flag_req, f_flag_msg, f_flag_additional,
    f_frag_num, f_window_size, f_checksum, f_data
}

-- flags types
local flag_types = {
    [0x80] = "FLAG_HS1",
    [0x88] = "FLAG_HS2",
    [0x89] = "FLAG_HS3",
    [0x40] = "FLAG_EXIT",
    [0x48] = "FLAG_EXIT_ACK",
    [0x20] = "FLAG_KEEPALIVE",
    [0x28] = "FLAG_KEEPALIVE_ACK",
    [0x12] = "FLAG_MSG",
    [0x1A] = "FLAG_MSG_ACK",
    [0x16] = "FLAG_MSG_REQ",
    [0x92] = "FLAG_MSG_PAR",
    [0x9A] = "FLAG_MSG_PAR_ACK",
    [0x96] = "FLAG_MSG_PAR_REQ",
    [0x13] = "FLAG_MSG_FRAG",
    [0x90] = "FLAG_DATA_PAR",
    [0x98] = "FLAG_DATA_PAR_ACK",
    [0x94] = "FLAG_DATA_PAR_REQ",
    [0x10] = "FLAG_DATA",
    [0x18] = "FLAG_DATA_ACK",
    [0x14] = "FLAG_DATA_REQ"
}

-- Dissector function
function myprotocol.dissector(buffer, pinfo, tree)
    -- if not enough data, it isnt my protocol
    if buffer:len() < 9 then
        return 0
    end

    pinfo.cols.protocol = "M. Kurcina's Protocol"

    local subtree = tree:add(myprotocol, buffer(), "M. Kurcina's Protocol Data")

    local flags = buffer(0, 1):uint()
    --name of flags type
    local flag_type = flag_types[flags] or "Unknown Type"
    subtree:add(f_flags, flag_type)

    -- individual flags
    local flag_tree = subtree:add("Individual Flags")
    flag_tree:add(f_flag_handshake, buffer(0, 1))
    flag_tree:add(f_flag_exit, buffer(0, 1))
    flag_tree:add(f_flag_keepalive, buffer(0, 1))
    flag_tree:add(f_flag_data, buffer(0, 1))
    flag_tree:add(f_flag_ack, buffer(0, 1))
    flag_tree:add(f_flag_req, buffer(0, 1))
    flag_tree:add(f_flag_msg, buffer(0, 1))
    flag_tree:add(f_flag_additional, buffer(0, 1))

    -- other fields
    subtree:add(f_frag_num, buffer(1, 4))
    subtree:add(f_window_size, buffer(5, 2))
    subtree:add(f_checksum, buffer(7, 2))

    -- if data is available, show field data
    local data_length = buffer:len() - 9
    if data_length > 0 then
        subtree:add(f_data, buffer(9, data_length))
    end
end

--register protocol for ports 1111 and 2222
local udp_table = DissectorTable.get("udp.port")
udp_table:add(1111, myprotocol)
udp_table:add(2222, myprotocol)
