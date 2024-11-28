import os
from collections import defaultdict
import re
import argparse

def read_data(file_name, ids):

    # Dictionary to store the results (defaults are int 0 and empty array)
    result = defaultdict(bytearray)
    secnums = defaultdict(int)

    # Pattern to match valid lines
    pattern = re.compile(r"^(\w+-\w+-\d{2})\s+([\w\s]+)$")

    with open(file_name, 'r') as file:
        for line in file:
            line = line.strip().upper()
            if not line:  # Skip empty lines
                continue

            match = pattern.match(line)
            if not match:  # Skip invalid lines
                continue

            full_id, data = match.groups()
            base_id, seq_num = '-'.join(full_id.split('-')[:2]), full_id.split('-')[-1]

            if len(ids) > 0 and base_id not in ids:
                #print(f"Skipping {base_id}, not in the searched list")
                continue  # Skip identifiers not in the list

            try:
                seq_num = int(seq_num)
            except ValueError:
                print(f"File: {file_name}, skipping invalid seq number {seq_num}")
                continue  # Skip if sequence number is not valid

            # Parse data and drop the last byte from the last group
            data_groups = data.split()
            if not all(len(group) != 2 for group in data_groups):  # Check valid hex groups
                #print(f"Expecting 3 groups of 4 hex digits each, got {data}")
                continue
            try:
                str = ''.join(group for group in data_groups)
                byte_data = bytearray.fromhex(str)
            except ValueError:
                print(f"File: {file_name}, expecting 3 groups of 4 hex digits each, got {data}")
                continue  # Skip if the data isn't valid hex

            # Verify sequence incrementing
            last_seq_num = secnums[base_id]
            if seq_num != last_seq_num + 1:
                print(f"File: {file_name}, expecting {base_id} with seq number {last_seq_num + 1}, but got {seq_num}")
                continue  # Skip if sequence is missing or not starting w/ 1

            result[base_id] += byte_data[:-1]
            secnums[base_id] = seq_num

    return dict(result)

def same_bits(array1, array2):
    return bytearray((0xff & (~(a ^ b))) for a, b in zip(array1, array2))

def not_bits(array1):
    return bytearray((0xff & (~a)) for a in array1)

def diff_bits(array1, array2):
    max_length = max(len(array1), len(array2))
    result = bytearray((a ^ b) for a, b in zip(array1, array2))
    return result.ljust(max_length, b'\xFF')

def do_and_bits_min(array1, array2):
    return bytearray((a & b) for a, b in zip(array1, array2))

def do_and_bits_max(array1, array2):
    max_length = max(len(array1), len(array2))
    result = bytearray((a & b) for a, b in zip(array1, array2))
    return result.ljust(max_length, b'\xFF')

def do_and_bits_max1(array1, array2):
    max_length = len(array1)
    if len(array2) < max_length:
        a2 = array2.ljust(max_length, b'\xFF')
    else:
        a2 = array2
    result = bytearray((a & b) for a, b in zip(array1, a2))
    return result

def eliminate_sames_with_mask(array1, array2, bitmask, seq_len):
    # Convert the byte arrays to binary strings
    mask = ''.join(f'{byte:08b}' for byte in bitmask)
    data1 = ''.join(f'{byte:08b}' for byte in array1)
    data2 = ''.join(f'{byte:08b}' for byte in array2)
    #print(f"mask: {mask}")
    #print(f"data1: {data1}")
    #print(f"data2: {data2}")
    if len(mask) > len(data1):
        data1.ljust(len(mask), 'a')
    if len(mask) > len(data2):
        data2.ljust(len(mask), 'b')
    # Prepare a new mask to store the result
    new_mask = [0] * len(mask)
    # Iterate over all valid sequences of `seq_len` long 1s in the mask
    for i in range(len(mask) - seq_len + 1):
        # Check if the current window contains only 1s
        if mask[i:i + seq_len] == '1' * seq_len:
            # Compare the data in the two arrays within this sequence
            if data1[i:i + seq_len] == data2[i:i + seq_len]:
                continue
            for j in range(i, i + seq_len):
                new_mask[j] |= 1
    # Convert the new mask back to a byte array
    return bytearray(int(''.join([str(x) for x in new_mask[i:i+8]]), 2) for i in range(0, len(new_mask), 8))    

def apply_value_filter(raw_data, bitmask, value_filter):
    # Prep data
    mask = ''.join(f'{byte:08b}' for byte in bitmask)
    data = ''.join(f'{byte:08b}' for byte in raw_data)
    val_filter_len = len(value_filter)
    # Prepare a new mask to store the result
    new_mask = [0] * len(mask)
    # Iterate over all long enough values comparing them to the target
    for i in range(min(len(mask), len(data)) - val_filter_len + 1):
        if mask[i:i + val_filter_len] != '1' * val_filter_len:
            continue
        if data[i:i + val_filter_len] != value_filter:
            continue
        for j in range(i, i + val_filter_len):
            new_mask[j] |= 1
    # Convert the new mask back to a byte array
    return bytearray(int(''.join([str(x) for x in new_mask[i:i+8]]), 2) for i in range(0, len(new_mask), 8))    

def pr_bits(iid, res, bit_seq_len=1):
    bit_string = ''.join(f'{byte:08b}' for byte in res)
    sequences = [(m.start(), m.end()) for m in re.finditer(f'1{{{bit_seq_len},}}', bit_string)]
    if not sequences:
        return 0

    lines_to_print = set()
    for start, end in sequences:
        start_line = start // 40
        end_line = (end - 1) // 40
        lines_to_print.update(range(start_line, end_line + 1))
        for line_num in range(start_line, end_line + 1):
            lines_to_print.add(line_num)

    for line_num, i in enumerate(range(0, len(bit_string), 40), start=0):
        if not line_num in lines_to_print:
            continue
        line = bit_string[i:i+40]
        formatted_line = ' '.join(line[j:j+4] for j in range(0, len(line), 4))
        print(f'  {iid}-{(line_num + 1):02d}: {formatted_line}')

    return 1

# Load the asbuilt data
def load_data():
    global dir_list, ids, bit_seq_min_len, data_dict

    if len(dir_list) == 0:
        dir_list = [d for d in os.listdir('.') if os.path.isdir(d) and not d.startswith('.')]
    for dir_name in dir_list:
        if os.path.isdir(dir_name):  # Check if directory exists
            data_dict[dir_name] = {}
            for file_name in os.listdir(dir_name):
                file_path = os.path.join(dir_name, file_name)
                if not file_name.startswith('.') and os.path.isfile(file_path):  # Check if it's a file and not special
                    data_dict[dir_name][file_name] = read_data(file_path, ids)
        else:
            print(f"\nDirectory '{dir_name}' does not exist.")
            return -1
    if len(ids) == 0:
        ids = list(set([id for aa in data_dict.values() for bb in aa.values() for id in bb.keys()]))
    return 0

# Print info about the loaded data
def print_scan_info():
    global dir_list, ids, bit_seq_min_len, data_dict

    count = 0
    for dir, files in data_dict.items():
        print(f"{dir}")
        count += 1
        for file, data in files.items():
            print(f"  {file}")
            count += 1
            for i in range(0, len(data.keys()), 10):
                print("    " + " ".join(list(data.keys())[i:i+10]))
                count += 1
    if count == 0:
        print("No data found, nothing to print")

# Find all bits that stay the same between all files in each folder
def find_same(dir_name):
    global dir_list, ids, bit_seq_min_len, data_dict

    files = data_dict[dir_name]
    #data_dict[dir_name][key_for_same] = {}
    file_names = list(files.keys())
    sames = {}
    for i in range(len(file_names)):
        file1 = file_names[i]
        if file1.startswith("__"): continue
        # start by comparing the first file w/ itsef, so we can handle 1-file folders
        for j in range(i, len(file_names)):
            file2 = file_names[j]
            if file2.startswith("__"): continue
            file1_ids = data_dict[dir_name][file1].keys()
            file2_ids = data_dict[dir_name][file2].keys()
            common_ids = list(set(file1_ids) & set(file2_ids))
            for iid in common_ids:
                res = same_bits(data_dict[dir_name][file1][iid], data_dict[dir_name][file2][iid])
                if iid in sames.keys():
                    agg_res = do_and_bits_min(sames[iid], res)
                else:
                    agg_res = res
                sames[iid] = agg_res
                #print(f"{dir_name} {file1} {file2} {iid} Same aggreg:")
                #pr_bits(iid, agg_res)

    # also need to eliminate missing keys
    for file_data in files.values():
        for key in list(sames.keys()):
            if key not in file_data.keys():
                del sames[key]

    data_dict[dir_name][key_for_same] = sames
    return sames

def print_same(dir_name):
    global dir_list, ids, bit_seq_min_len, data_dict

    find_same(dir_name)
    print(f"Bitmask for data bits that are the same across files in {dir_name}")
    if value_filter != None:
        a_file_data = next(iter(data_dict[dir_name].values()))
        print(f"Value filter: {value_filter}")
    count = 0
    for iid, res in data_dict[dir_name][key_for_same].items():
        if value_filter != None:
            res = apply_value_filter(a_file_data[iid], res, value_filter)
        if pr_bits(iid, res, bit_seq_min_len) > 0:
            print("")
            count += 1
    if count <= 0:
        print("  Nothing was found")

def print_not_same(dir_name):
    global dir_list, ids, bit_seq_min_len, data_dict

    find_same(dir_name)
    print(f"Bitmask for data bits that are not the same across files in {dir_name}")
    count = 0
    for iid, res in data_dict[dir_name][key_for_same].items():
        not_res = not_bits(res)
        if pr_bits(iid, not_res, bit_seq_min_len) > 0:
            print("")
            count += 1
    if count <= 0:
        print("  Nothing was found")

def print_same_but_diff(dir_name, seq_len):
    for dir in dir_list:
        find_same(dir)
        #for iid, res in data_dict[dir][key_for_same].items():
        #    print(f"{dir} {iid} sames:")
        #    pr_bits(iid, data_dict[dir][key_for_same][iid])
    # list for accumulating results
    res_list = {}
    for iid, res in data_dict[dir_name][key_for_same].items():
        res_list[iid] = res
    # comapre target dir sames w/ all others and construct intersection of the smaes bitmasks
    for dir in dir_list:
        if dir_name == dir:
            continue
        # go over each iid block of data
        for iid, res in res_list.items():
            if iid not in data_dict[dir][key_for_same].keys():
                continue
            res_list[iid] = do_and_bits_max1(res_list[iid], data_dict[dir][key_for_same][iid])
            #print(f"{dir} intersected {iid} sames:")
            #pr_bits(iid, res_list[iid])
    # eliminate from the results any bits that do not end up in mismatching sequences of
    # bit_seq_min_len long. Since only looking at the "sames" data from any file in a dir can
    # be used for the comparison. For example, 
    # dir1.file1.id1 =  "01101101100"
    # dir1.file2.id1 =  "00101100010"
    # dir2.file1.id1 =  "01101001010"
    # ---- sames for the dir1 and dir2 ---
    # dir1.__same.id1 = "10111110001"
    # dir2.__same.id1 = "11111111111" (just one file in dir2 -> no differences)
    # ---- intersection of sames ---
    # intersection =    "10111110001"
    # --- remove any identical across dirs 3 bit long sequences ---
    # Candidate masks:  "00111000000", "00011100000", "00001110000"
    # Masked values 1:  "xx101xxxxxx", "xxx011xxxxx", "xxxx110xxxx"
    # Masked values 2:  "xx101xxxxxx", "xxx010xxxxx", "xxxx100xxxx"
    # Result id1 mask:  "00000000000" |"00011100000"| "00001110000" = "00011110000"
    # -------------
    # The below loop does the
    #    remove any identical across dirs seq_len bit long sequences
    # step. Note that we can use any dir file values for comparison as
    # we masked the same bits and only going to be comparing those.
    data1_list = next(iter(data_dict[dir_name].values())) 
    for dir in dir_list:
        if dir_name == dir:
            continue
        data2_list = next(iter(data_dict[dir].values())) 
        # go over each iid block of data doing the elimination
        for iid, res in res_list.items():
            data1 = data1_list[iid]
            if iid not in data2_list.keys():
                continue
            data2 = data2_list[iid]
            new_res = eliminate_sames_with_mask(data1, data2, res, seq_len)
            res_list[iid] = new_res
    # print the results        
    print(f"Bitmask for data bits staying same within all dirs, but")
    print(f"containing {seq_len}-bit long values not matching those in {dir_name}")
    if value_filter != None:
        a_file_data = next(iter(data_dict[dir_name].values()))
        print(f"Value filter: {value_filter}")
    count = 0
    for iid, res in res_list.items():
        if value_filter != None:
            res = apply_value_filter(a_file_data[iid], res, value_filter)
        if pr_bits(iid, res, bit_seq_min_len) > 0:
            print("")
            count += 1
    if count <= 0:
        print("  Nothing was found")

#================================================================================================
# This code helps reverse-engineering vehicle asbuilt data retrieved from
# https://www.motorcraftservice.com/asbuilt
# (note: cut/paste the table into text files, no psupport for the xml they offer to download)
# It finds positions of the bits matching various criteria.
# At the end it prints out all the data blocks that contain the matching bits (marked by 1s in
# the printouts).
#=================================================================================================

# List of directories, e.g. dir_list = ["34g", "48g"]
# (autofilled unless passed from the command line)
dir_list = []
# Data blocks to examine, e.g. ids = ["7E0-162", "7E0-163", "7E0-165"]
# (autofilled unless passed from the command line)
ids = []
# minimum length of the bit sequence to search for 
# (used for several search types, has to be passed as a parameter)
bit_seq_min_len = 1
# keys for some special data
key_for_same = "__same"
# string of 0s and 1s representing binary value to search for in masked
# data values for the target dir files (only makes sense for --print-same...
# i.e. it assumes the masked data is the same for all dir files)
value_filter = None

# Dictionary to store the data (the main data storage)
data_dict = {}

def main():
    global dir_list, ids, bit_seq_min_len, data_dict, value_filter

    # Create the argument parser
    parser = argparse.ArgumentParser(description="Process and analyze directories and binary data.")
    
    # Add arguments
    parser.add_argument(
        "--dirs",
        type=str,
        nargs="+",
        required=False,
        help="List of directories to process."
    )
    parser.add_argument(
        "--ids",
        type=str,
        nargs="+",
        required=False,
        help="List of IDs to scan (e.g., '7E0-162')."
    )
    parser.add_argument(
        "--print-scan-info",
        action="store_true",
        help="Print the information about scanned dirs, files and IDs."
    )
    parser.add_argument(
        "--add-value-filter",
        type=str,
        help="A string of 0s and 1s representing a binary value to search for in the masked data (makes sens only for --print-same...)."
    )
    parser.add_argument(
        "--print-same",
        type=str,
        nargs=2,
        metavar=("DIR", "SLEN"),
        help="Find sequences of bits of length SLEN or more that are the same for all the files in the directory."
    )
    parser.add_argument(
        "--print-not-same",
        type=str,
        nargs=2,
        metavar=("DIR", "SLEN"),
        help="Find sequences of bits of length SLEN or more that are not the same (negation of --print-same)."
    )
    parser.add_argument(
        "--print-same-but-diff",
        type=str,
        nargs=2,
        metavar=("DIR", "SLEN"),
        help="Find all sequences of bits of length SLEN that are the same for all files in each directory, but " + 
             "contain different SLEN-bit-long values as compared between the target dir and all others."
    )

    # Parse the arguments
    args = parser.parse_args()

    if args.dirs:
        dir_list = args.dirs

    if args.ids:
        ids = args.ids

    print("Loading data...", end="")
    if load_data() != 0:
        exit(-1)
    print("Done")

    if args.print_scan_info:
        print_scan_info()

    if args.add_value_filter:
        value_filter = args.add_value_filter

    if args.print_same:
        dir = args.print_same[0]
        if not dir in data_dict.keys():
            print(f"No dir \"{dir}\" in the data!")
            exit(-2)
        val = args.print_same[1]
        if not val.isdigit():
            print(f"Minimum sequence length \"{val}\" is not a digit")
            exit(-3)
        bit_seq_min_len = int(val)
        print_same(dir)

    if args.print_not_same:
        dir = args.print_not_same[0]
        if not dir in data_dict.keys():
            print(f"No dir \"{dir}\" in the data!")
            exit(-4)
        val = args.print_not_same[1]
        if not val.isdigit():
            print(f"Minimum sequence length \"{val}\" is not a digit")
            exit(-5)
        bit_seq_min_len = int(val)
        print_not_same(dir)

    if args.print_same_but_diff:
        dir = args.print_same_but_diff[0]
        if not dir in data_dict.keys():
            print(f"No dir \"{dir}\" in the data!")
            exit(-6)
        val = args.print_same_but_diff[1]
        if not val.isdigit():
            print(f"Minimum sequence length \"{val}\" is not a digit")
            exit(-7)
        seq_len = bit_seq_min_len = int(val)
        print_same_but_diff(dir, seq_len)

# Call main
if __name__ == "__main__":
    main()
