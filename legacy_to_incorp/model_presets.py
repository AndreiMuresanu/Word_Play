from word_play.model import Model
from math import inf
from openai import OpenAI
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig, BitsAndBytesConfig
from tqdm import tqdm


# NOTE: We create the OPENAI_CLIENT variable because if it is an attribute of the ChatGPT class,
#	it prevents fuctionaility such as deepcopying the ChatGPT class. We initially set it to None
#	because other models may not need it.
# NOTE: To use this openai client, you much have the OPENAI_API_KEY environment variable set
# TODO: This can likely be made nicer
OPENAI_CLIENT = None

# TODO: this is a nasty way to have the Model class not store and only reference the LLM
HUGGINGFACE_MODELS = {}
HUGGINGFACE_TOKENIZERS = {}


class Human(Model):

	def generate_text(self, input_text, generation_config=None):
		return input(f"""
========================= input START =========================
{input_text}
HUMAN input: """)
	
	# TODO: extend the prompt to work when multiple inputs are given
	# TODO: add some text validation to keep prompting the user until they input a valid list
	def cond_logP(self, inputs: str | list[str], targets: list[str] | list[list[str]]) -> float | list[float]:
		assert type(inputs) == str, 'batching not yet supported for Human Model'
		assert type(targets) == list and type(targets[0]) == str, 'batching not yet supported for Human Model'

		prompt_str = f'\n========================= input START =========================' \
					 f'\n{inputs}' \
					 f'\n========================= inputs END =========================' \
					 f'\n========================= targets START ========================='
		for idx, target in enumerate(targets):
			prompt_str += f'\n------------------------- target {idx} -------------------------\n{target}'
		
		prompt_str += '\n========================= targets END ========================='
		prompt_str += f'\nOutput a list of {len(targets)} probabilities (ex., "[0.3, 0.2, 0.5]"): '

		return [float(elm) for elm in input(prompt_str).strip()[1:-1].split(',')]


class ChatGPT(Model):

	def __init__(self, model_name:str, system_prompt: str, model_params: dict, verbosity: int=0) -> None:
		super().__init__(verbosity=verbosity)
		global OPENAI_CLIENT
		OPENAI_CLIENT = OpenAI()
		self.model_name = model_name
		self.system_prompt = system_prompt
		self.model_params = model_params


	# NOTE: OpenAI has very limited access to log probs, this is a hacky workaround to get log probs
	# TODO: maybe convert this to take as input of inputs and give logP for a list of lists containing targets
	# TODO: silent error if choice is not 1 token (this will result in always getting a prob of 0)
	def logP_of_choices(self, prompt, choices=[]):
		raise NotImplementedError()
		input_params = self.build_model_input(prompt, choices)
		response = OPENAI_CLIENT.chat.completions.create(**input_params)

		logprobs = {choice:-inf for choice in choices}	# set default logP values
		for token_logP_info in response.choices[0].logprobs.content[0].top_logprobs:
			if token_logP_info['token'] in logprobs:
				logprobs[token_logP_info['token']] = token_logP_info['logprob']
		
		return logprobs
	

	# TODO: support batched inputs (just set batch size to 1 because openai doesn't support larger batch sizes)
	def generate_text(self, input_text, generation_config=None):
		if self.verbosity >= 2:	print('generating text...')	# TODO: maybe more this text to the Model class?

		if generation_config:
			# we override the model params with the generation config
			generation_config = self.model_params | generation_config
		else:
			generation_config = self.model_params

		return OPENAI_CLIENT.chat.completions.create(
			model=self.model_name,
			messages=[
				{"role": "system", "content": self.system_prompt},
				{"role": "user", "content": input_text}
			],
			**generation_config
		).choices[0].message.content


# TODO: We likely want a general HuggingFace Model class instead
# TODO: Im hard coding some things, just to make things easy. Will generalize later
class Llama3_Chat(Model):

	def __init__(self, model_name: str, system_prompt: str, model_params: dict, batch_size=1, verbosity=0) -> None:
		super().__init__(verbosity)

		# TODO: uncomment
		# assert 'Instruct' in model_name
		self.model_name = model_name
		self.system_prompt = system_prompt
		self.model_params = model_params
		self.batch_size = batch_size
		
		if self.model_name not in HUGGINGFACE_MODELS:
			if '70B' in self.model_name:
				quantization_config = BitsAndBytesConfig(
					load_in_4bit=True,
					bnb_4bit_compute_dtype=torch.float16,
					bnb_4bit_quant_type="nf4",
					bnb_4bit_use_double_quant=True,
				)
			else:
				quantization_config=None
			
			HUGGINGFACE_MODELS[self.model_name] = AutoModelForCausalLM.from_pretrained(
																			model_name,
																			device_map="auto",
																			torch_dtype=torch.bfloat16,
																			attn_implementation="flash_attention_2",
																			quantization_config=quantization_config,
																		)
		if self.model_name not in HUGGINGFACE_TOKENIZERS:
			tokenizer = AutoTokenizer.from_pretrained(
											model_name,
											padding_side='left'
										)
			tokenizer.pad_token = tokenizer.eos_token
			tokenizer.pad_token_id = tokenizer.eos_token_id
			HUGGINGFACE_TOKENIZERS[self.model_name] = tokenizer


	def generate_text(self, input_text: str | list[str], generation_params=None):
		if self.verbosity >= 2:	print('generating text...')	# TODO: maybe more this text to the Model class?

		if type(input_text) == str:
			input_text = [input_text]
			convert_back_to_str = True
		else:
			convert_back_to_str = False

		if generation_params:
			# we override the model params with the generation config
			generation_params = self.model_params | generation_params
		else:
			generation_params = self.model_params

		# 1: Load the model and tokenizer
		model = HUGGINGFACE_MODELS[self.model_name]
		tokenizer = HUGGINGFACE_TOKENIZERS[self.model_name]

		chats = []
		for text in input_text:
			chats.append([
				{"role": "system", "content": self.system_prompt},
				{"role": "user", "content": text}
			])

		# 2: Apply the chat template
		formatted_chats = tokenizer.apply_chat_template(chats, tokenize=False, add_generation_prompt=True)
		
		# 3: Tokenize the chat (This can be combined with the previous step using tokenize=True)
		inputs = tokenizer(formatted_chats, return_tensors="pt", add_special_tokens=True, padding=True)
		
		# Move the tokenized inputs to the same device the model is on (GPU/CPU)
		inputs = {key: tensor.to(model.device) for key, tensor in inputs.items()}

		# prevent model from generating multiple messages
		gen_config = GenerationConfig(
			eos_token_id=[tokenizer.eos_token_id, tokenizer.convert_tokens_to_ids("<|eot_id|>")],
		)

		# 4: Generate text from the model
		outputs = model.generate(
						**inputs,
						generation_config=gen_config,
						**generation_params
					)
		
		# 5: Decode the output back to a string
		# all inputs have the same length because of padding so inputs['input_ids'].size(1) with all outputs
		decoded_outputs = tokenizer.batch_decode(
										[outputs[i][inputs['input_ids'].size(1):] for i in range(len(outputs))],
										skip_special_tokens=True
									)

		if convert_back_to_str:
			return decoded_outputs[0]
		else:
			return decoded_outputs


	def _logP_of_tokens(self, inputs):
		outputs = HUGGINGFACE_MODELS[self.model_name](input_ids=inputs['input_ids'], attention_mask=inputs['attention_mask']).logits.to(torch.float32)
		probs = torch.log_softmax(outputs, dim=-1).detach()

		# collect the probability of the generated token -- probability at index 0 corresponds to the token at index 1
		probs = probs[:, :-1, :]
		input_ids = inputs['input_ids'][:, 1:]
		gen_probs = torch.gather(probs, 2, input_ids[:, :, None]).squeeze(-1)

		return gen_probs


	def _logP_of_targets(self, inputs: list[str], targets: list[str]) -> list[float]:
		'''
		NOTE: "<|begin_of_text|>" and chat related tokens should be present in the inputs and targets as strings
		'''
		assert len(inputs) == len(targets), 'inputs and targets must have the same length'

		tokenizer = HUGGINGFACE_TOKENIZERS[self.model_name]

		tokenized_inputs = [tokenizer(elm, padding=False, return_tensors='pt', add_special_tokens=False) for elm in inputs]
		tokenized_targets = [tokenizer(elm, padding=False, return_tensors='pt', add_special_tokens=False) for elm in targets]

		for inp, tar in zip(tokenized_inputs, tokenized_targets):
			assert inp['input_ids'][0][0] == tokenizer.bos_token_id, f"inp['input_ids'][0][0]: {inp['input_ids'][0][0]} != {tokenizer.bos_token_id}"
			assert inp['input_ids'][0][1] != tokenizer.bos_token_id, f"inp['input_ids'][0][1]: {inp['input_ids'][0][1]} == {tokenizer.bos_token_id}"
			assert tar['input_ids'][0][0] != tokenizer.bos_token_id, f"tar['input_ids'][0][0]: {tar['input_ids'][0][0]} == {tokenizer.bos_token_id}"

		num_target_tokens = [len(seq['input_ids'][0]) for seq in tokenized_targets]

		# Merge inputs and targets	
		max_len = -1
		merged_ids = []
		for inp, tar in zip(tokenized_inputs, tokenized_targets):

			assert len(tar['input_ids']) == 1
			assert len(inp['input_ids']) == 1
			merged_elm_ids = torch.cat((inp['input_ids'][0], tar['input_ids'][0]))
			
			if len(merged_elm_ids) > max_len:
				max_len = len(merged_elm_ids)
			
			merged_ids.append(merged_elm_ids)

		# Manually pad the merged_ids and create attention mask
		attention_mask = []
		for idx, ids in enumerate(merged_ids):
			if len(ids) < max_len:
				merged_ids[idx] = torch.cat((torch.full(
													size=(max_len - len(ids),),
													fill_value=torch.tensor(tokenizer.pad_token_id, dtype=torch.int),
													dtype=torch.int
												), merged_ids[idx]))
			attention_mask.append(torch.cat((torch.zeros(max_len - len(ids), dtype=torch.int), torch.ones(len(ids), dtype=torch.int)) ))
		
		attention_mask = torch.stack(attention_mask)
		merged_ids = torch.stack(merged_ids)
		logP_input = {'input_ids': merged_ids, 'attention_mask': attention_mask}

		logP_of_merged_ids = self._logP_of_tokens(logP_input)

		logP_of_target_tokens = [logProbs[len(logProbs) - token_count:] for token_count, logProbs in zip(num_target_tokens, logP_of_merged_ids)]

		return [float(torch.mean(seq)) for seq in logP_of_target_tokens]

	
	def _remove_generation_prompt(self, inputs: list[str]):
		# apply_chat_template(add_generation_prompt=False) is not working correctly, issue: https://github.com/huggingface/transformers/issues/30893
		# NOTE: we edit the string instead of tokens because dealing with attention mask and things like that is annoying

		generation_prompt = "<|start_header_id|>assistant<|end_header_id|>\n\n"
		for i in range(len(inputs)):
			assert inputs[i][-len(generation_prompt):] == generation_prompt, f'input[-len(generation_prompt):] = {inputs[i][-len(generation_prompt):]} != {generation_prompt}'
			inputs[i] = inputs[i][:-len(generation_prompt)]
		
		return inputs
	
	
	def _remove_beginning_of_seq_token(self, inputs: list[str], bos_token: str):
		# NOTE: we edit the string instead of tokens because dealing with attention mask and things like that is annoying
		# TODO: we should use tokens instead of strings

		for i in range(len(inputs)):
			assert inputs[i][:len(bos_token)] == bos_token, f'input[-len(bot_token):] = {inputs[i][-len(bos_token):]} != {bos_token}'
			inputs[i] = inputs[i][len(bos_token):]
		
		return inputs


	def cond_logP(self, inputs: str | list[str], targets: list[str] | list[list[str]]) -> float | list[float]:

		if type(inputs) == str and type(targets) == list and type(targets[0]) == str:
			inputs = [inputs]
			targets = [targets]
			convert_back_to_str = True
		elif type(inputs) == list and type(inputs[0]) == str and type(targets) == list and type(targets[0]) == list and type(targets[0][0]) == str:
			convert_back_to_str = False
		else:
			raise ValueError('Invalid types recieved. Must have: inputs: str | list[str], targets: list[str] | list[list[str]]')

		# Create chat messages
		input_chats = []
		for input in inputs:
			input_chats.append([
				{"role": "system", "content": self.system_prompt},
				{"role": "user", "content": input}
			])
		
		target_chats = []
		for target_batch in targets:
			cur_inp_targets = []
			for target in target_batch:
				cur_inp_targets.append([
					{"role": "assistant", "content": target}
				])
			target_chats.append(cur_inp_targets)

		# Format chat messages
		formatted_inputs = HUGGINGFACE_TOKENIZERS[self.model_name].apply_chat_template(input_chats, tokenize=False, add_generation_prompt=True)
		formatted_inputs = self._remove_generation_prompt(formatted_inputs)

		formatted_targets = [HUGGINGFACE_TOKENIZERS[self.model_name].apply_chat_template(chats_per_inp, tokenize=False, add_generation_prompt=True) for chats_per_inp in target_chats]
		formatted_targets = [self._remove_generation_prompt(tars) for tars in formatted_targets]
		bos_token = HUGGINGFACE_TOKENIZERS[self.model_name].bos_token
		formatted_targets = [self._remove_beginning_of_seq_token(tars, bos_token) for tars in formatted_targets]

		expanded_inputs = []
		expanded_targets = []
		for cur_input, target_options in zip(formatted_inputs, formatted_targets):
			for tar_opt in target_options:
				expanded_inputs.append(cur_input)
				expanded_targets.append(tar_opt)

		input_batches = [expanded_inputs[i:i+self.batch_size] for i in range(0, len(expanded_inputs), self.batch_size)]
		target_batches = [expanded_targets[i:i+self.batch_size] for i in range(0, len(expanded_targets), self.batch_size)]

		raw_logProbs = []
		for cur_input_batch, cur_target_batch in tqdm(zip(input_batches, target_batches), total=len(input_batches), desc='logP batches'):
			raw_logProbs += self._logP_of_targets(inputs=cur_input_batch, targets=cur_target_batch)

		per_ex_log_probs = []
		cur_raw_logP_idx = 0
		for target_group in targets:
			per_ex_log_probs.append(raw_logProbs[cur_raw_logP_idx : cur_raw_logP_idx + len(target_group)])
			cur_raw_logP_idx += len(target_group)

		# if self.verbosity >= 2:
		# 	for i, (cur_input, target_options) in enumerate(list(zip(inputs, targets))[:3]):
		# 		print(f'---------------------- {i} ----------------------')
		# 		print(f'INPUT:', cur_input)
		# 		print('TARGETS:')
		# 		for target, logP in zip(target_options, per_ex_log_probs[i]):
		# 			print(f'{round(logP, 2):.2f}, {target}')

		if convert_back_to_str:
			targets = targets[0]
			per_ex_log_probs = per_ex_log_probs[0]

		return per_ex_log_probs
