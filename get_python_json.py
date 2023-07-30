"""
Generates JSON format question-answer pairs and instructions for a Python file
Requirements:
[req01] The get_model function shall accept a dictionary containing the model
        configuration as an argument. It should import the specified model 
        class using the information from the model configuration, instantiate
        the model class with the provided parameters from the model 
        configuration, and return the instantiated model.
[req02] The PythonJsonGenerator class shall parse a Python file, a list of 
        questions, and generate JSON-formatted question-answer pairs and
        instructions.
[req03] The PythonJsonGenerator class shall add the generated question-answer
        pairs to the qa_list attribute.
[req04] The PythonJsonGenerator class shall add the generated instructions to
        the instruct_list attribute.
[req05] The PythonJsonGenerator class shall use a language model to generate
        responses if the use_llm attribute is set to True.
[req06] The PythonJsonGenerator class shall handle exceptions that may occur
        during loading the language model.
[req07] The PythonJsonGenerator class shall generate and return qa_list and
        instruct_list when the generate method is called.
[req08] The PythonJsonGenerator class shall use the get_model function to load
        the specified language model according to the configuration file.
[req09] The PythonJsonGenerator class shall use the loaded language model to
        generate responses to the questions.
[req10] The PythonJsonGenerator class shall handle exceptions that may occur
        during the generation of responses.
[req11] The get_python_json function shall create an instance of
        PythonJsonGenerator and call the generate method.
[req12] The get_python_json function shall return qa_list and instruct_list
        generated by the PythonJsonGenerator instance.
[req13] The PythonJsonGenerator class shall read the configuration file to set
        the inference model parameters.
"""
import re
import os
import json
import logging
import importlib
import yaml
from typing import List, Dict

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO)
logger = logging.getLogger(__name__)

def get_model(model_config: dict) -> object:
    """
    Imports and instantiates a model based on the provided configuration.
    Args:
        model_config (dict): A dictionary containing the configuration for the
            model. It should include the import path for the model class and
            parameters for instantiation.
    Returns:
        object: An instance of the specified model class, or None if there was
            an error.
    """
    model = None
    try:
        module_name, class_name = model_config['model_import_path'].rsplit('.', 1)
        module = importlib.import_module(module_name)
    except ImportError as e:
        print(f"Failed to import module {module_name}. Error: {e}")
        return model
    try:
        ModelClass = getattr(module, class_name)
    except AttributeError as e:
        print(f"Module {module_name} does not have a class named {class_name}. Error: {e}")
        return model
    model_params = model_config['model_params']
    try:
        model = ModelClass.from_pretrained(model_params.pop('model_path'), **model_params)
    except Exception as e:
        print(f"Failed to instantiate the model with the provided parameters. Error: {e}")
        return model
    return model

class PythonJsonGenerator:
    """
    A class used to generate JSON formatted dictionary outputs for a Python 
    file.
    Attributes:
        file_path (str): The path to the Python file.
        file_details (Dict): A dictionary containing details of the Python
            file.
        base_name (str): The base name of the Python file.
        questions (List): A list of questions for which responses are to be
            generated.
        qa_list (List): A list to store the generated question-answer pairs.
        instruct_list (List): A list to store the generated instructions.
        question_mapping (Dict): A dictionary mapping question types to their
            corresponding keys in the file details.
        use_llm (bool): A flag indicating whether to use a language model for
            generating responses.
        llm (AutoModelForCausalLM): The language model to be used for
            generating responses.
    Methods:
        clean_and_get_unique_elements(input_str: str) -> str: Cleans an input 
            string and returns a string of unique elements.
        add_to_list(list_to_update: List[Dict], query: str, response: str,
            additional_field=None) -> List[Dict]: Adds a response to a list.
        get_response_from_llm(query: str, context: str) -> str: Gets a 
            response from the language model.
        get_variable_purpose(question_id: str, question_text: str, base_name:
            str, name: str, info: Dict, context: str, variable_type: str) -> 
                None: Processes questions related to the purpose of a variable.
        process_question(question_id: str, query: str, context: str, info) -> 
            None: Processes a question and adds the generated response to the
            qa_list and instruct_list.
        process_file_question(question_id: str, question_text: str) -> None:
            Processes questions related to a file.
        process_func_class_question(question_type: str, question_id: str, 
            question_text: str) -> None: Processes questions related to a 
            function or class.
        generate() -> Tuple[List[Dict], List[Dict]]: Generates responses for
            all the questions and returns the qa_list and instruct_list.
    """
    def __init__(self, file_path: str, file_details: Dict, base_name: str, questions: List[Dict], use_llm: bool, config: Dict):
        self.file_path = file_path
        self.file_details = file_details
        self.base_name = base_name
        self.questions = questions
        self.qa_list = []
        self.instruct_list = []
        self.question_mapping = {
            'file': 'file',
            'function': 'functions',
            'class': 'classes',
            'method': 'classes'
        }
        self.use_llm = use_llm
        self.config = config

        if self.use_llm:
            try:
                self.llm_config = config['inference_model']
                self.llm = get_model(self.llm_config)
            except (FileNotFoundError, yaml.YAMLError, ImportError, AttributeError) as e:
                logger.error(f'Failed to load configuration file: {e}')
                self.use_llm = False
                self.llm_config = None
                self.llm = None
        else:
            self.llm = None

    @staticmethod
    def clean_and_get_unique_elements(input_str: str) -> str:
        cleaned_elements = set(re.sub(r'[^\w\-_>\s:/.]', '', element.strip())
                               for element in re.sub(r'\s+', ' ', input_str).split(','))
        return ', '.join(cleaned_elements)

    @staticmethod
    def add_to_list(list_to_update: List[Dict], query: str, response: str, additional_field=None) -> List[Dict]:
        if response and response.strip() and response != 'None':
            list_to_update.append(
                {'instruction': query, 'input' : additional_field, 'output': response}
                if additional_field else
                {'question': query, 'answer': response}
            )
        return list_to_update

    def get_response_from_llm(self, query: str, context: str) -> str:
        if not self.llm:
            logger.error('AI model not available.')
            return ''
        prompt = self.config["prompt_template"].format(context=context, query=query)
        logging.info(f'Query: {query}')
        response = self.llm(prompt)
        logging.info(f'Response: {response}')
        return response

    def process_items(self, question_id: str, question_text: str, base_name: str, name: str, info: Dict, context: str, item_type: str) -> None:
        if info[item_type]:
            items = [item.strip() for item in self.clean_and_get_unique_elements(str(info[item_type])).split(',') if item]
            for item in items:
                query = question_text.format(filename=base_name, **{f'{item_type.split("_")[0]}_name': name, f'{item_type.split("_")[0]}_variable': item})
                self.process_question(question_id, query, context, info)

    def process_question(self, question_id: str, query: str, context: str, info) -> None:
        if question_id.endswith('code_graph'):
            response = info.get(question_id, {})
        else:
            response = self.get_response_from_llm(query, context) if self.use_llm and question_id.endswith('purpose') else self.clean_and_get_unique_elements(str(info.get(question_id, '')))
        if response and response != 'None':
            response_str = str(response)
            response_str = response_str.strip()
            if response_str:
                self.qa_list.append({'question': query, 'answer': response_str})
                self.instruct_list.append({'instruction': query, 'input': context, 'output': response_str})

    def process_file_question(self, question_id: str, question_text: str) -> None:
        query = question_text.format(filename=self.base_name)
        context = self.file_details['file_info']['file_code']
        info = self.file_details['file_info']
        self.process_question(question_id, query, context, info)

    def process_func_class_question(self, question_type: str, question_id: str, question_text: str) -> None:
        if question_type == 'method':  
            for class_name, class_info in self.file_details['classes'].items():
                for key, method_info in class_info.items():
                    if key.startswith('class_method_'):
                        method_name = key[len('class_method_'):]
                        context = method_info['method_code']
                        mapping = {'class_name': class_name, 'method_name': method_name}
                        query = question_text.format(filename=self.base_name, **mapping)
                        self.process_question(question_id, query, context, method_info)
        else:
            for name, info in self.file_details[self.question_mapping[question_type]].items():
                context = info[f'{question_type}_code']
                mapping = {f'{question_type}_name': name}
                if question_id == f'{question_type}_variable_purpose' and self.use_llm:
                    self.process_items(question_id, question_text, self.base_name, name, info, context, f'{question_type}_variables')
                elif question_id != f'{question_type}_variable_purpose':
                    query = question_text.format(filename=self.base_name, **mapping)
                    self.process_question(question_id, query, context, info)

    def generate(self) -> tuple[List[Dict], List[Dict]]:
        for question in self.questions:
            question_id = question['id']
            question_text = question['text']
            question_type = question['type']
            if question_type == 'file':
                self.process_file_question(question_id, question_text)
            elif question_type in ['function', 'class', 'method']:
                self.process_func_class_question(question_type, question_id, question_text)
        return self.qa_list, self.instruct_list


def get_python_json(file_path: str, file_details: Dict, base_name: str, questions: List[Dict], use_llm: bool) -> tuple[List[Dict], List[Dict]]:
    """
    Extract information from a Python file and return it in JSON format.
    Args:
        file_path (str): The path to the Python file.
        file_details (Dict): The details of the file.
        base_name (str): The base name.
        questions (List[Dict]): The list of questions.
        use_llm (bool): Whether to use the language model.
    Returns:
        Tuple[List[Dict], List[Dict]]: Extracted information in JSON format.
    """
    # Load the configuration from the YAML file
    with open('model_config.yaml', 'r') as config_file:
        config = yaml.safe_load(config_file)
    generator = PythonJsonGenerator(file_path, file_details, base_name, questions, use_llm, config)
    return generator.generate()