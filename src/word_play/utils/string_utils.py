import re


def extract_number_surrounded_by_quotes(input_str):
	'''Given a string such as 'some text "1" more text "5" even more text', this function returns 5'''
	return int(re.findall('"\d+"', input_str)[-1][1:-1])


def remove_potential_leading_and_trailing_quotes(input_str):
	input_str = input_str.strip()
	if input_str.startswith('"'):
		input_str = input_str[1:]
	if input_str.endswith('"'):
		input_str = input_str[:-1]
	return input_str.strip()
